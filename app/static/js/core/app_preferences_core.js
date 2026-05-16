// ── App preference pure helpers ───────────────────────────────────────────
// Loaded before app.js. Storage, cookies, and DOM sync stay in app.js; the
// supported values and snapshot normalization live here.
(function (global) {
  const SESSION_PREFERENCE_KEYS = Object.freeze([
    'pref_active_project_id',
    'pref_theme_name',
    'pref_timestamps',
    'pref_line_numbers',
    'pref_welcome_intro',
    'pref_share_redaction_default',
    'pref_project_auto_link_external_runs',
    'pref_run_notify',
    'pref_hud_clock',
    'pref_prompt_username',
    'pref_compare_view_mode',
    'pref_compare_context',
    'pref_options_modal_last_tab',
    'pref_tour_seen_version',
  ]);
  const WELCOME_INTRO_MODES = Object.freeze(['animated', 'disable_animation', 'remove']);
  const SHARE_REDACTION_DEFAULT_MODES = Object.freeze(['unset', 'redacted', 'raw']);
  const HUD_CLOCK_MODES = Object.freeze(['utc', 'local']);
  const COMPARE_VIEW_MODES = Object.freeze(['auto', 'side_by_side', 'unified', 'changes_only', 'findings_only']);
  const COMPARE_CONTEXT_MODES = Object.freeze(['3', '10', 'all']);
  const OPTIONS_MODAL_TABS = Object.freeze(['preferences', 'secrets']);

  function _coerceMode(value, modes, fallback) {
    return modes.includes(value) ? value : fallback;
  }

  function coerceTimestampMode(value, modes = ['off', 'elapsed', 'clock']) {
    return _coerceMode(value, modes, 'off');
  }

  function coerceLineNumberMode(value) {
    return value === 'on' ? 'on' : 'off';
  }

  function coerceWelcomeIntroMode(value) {
    return _coerceMode(value, WELCOME_INTRO_MODES, 'animated');
  }

  function coerceShareRedactionDefaultMode(value) {
    return _coerceMode(value, SHARE_REDACTION_DEFAULT_MODES, 'unset');
  }

  function coerceRunNotifyMode(value) {
    return value === 'on' ? 'on' : 'off';
  }

  function coerceHudClockMode(value) {
    return _coerceMode(value, HUD_CLOCK_MODES, 'utc');
  }

  function coerceCompareViewMode(value) {
    return _coerceMode(value, COMPARE_VIEW_MODES, 'auto');
  }

  function coerceCompareContextMode(value) {
    const normalized = String(value || '').trim().toLowerCase();
    return _coerceMode(normalized, COMPARE_CONTEXT_MODES, '3');
  }

  function coerceOptionsModalTab(value) {
    const normalized = String(value || '').trim().toLowerCase();
    return _coerceMode(normalized, OPTIONS_MODAL_TABS, 'preferences');
  }

  function normalizePromptUsername(value) {
    const username = String(value || '').trim();
    return /^[A-Za-z0-9._-]{1,32}$/.test(username) ? username : '';
  }

  function coerceTourSeenVersion(value) {
    if (value === null || typeof value === 'undefined' || value === '') return '';
    const parsed = Number.parseInt(String(value).trim(), 10);
    return Number.isFinite(parsed) && parsed >= 1 ? parsed : '';
  }

  function defaultSessionPreferences(defaultTheme = 'darklab_obsidian.yaml') {
    return {
      pref_theme_name: defaultTheme || 'darklab_obsidian.yaml',
      pref_active_project_id: '',
      pref_timestamps: 'off',
      pref_line_numbers: 'off',
      pref_welcome_intro: 'animated',
      pref_share_redaction_default: 'unset',
      pref_project_auto_link_external_runs: 'on',
      pref_run_notify: 'off',
      pref_hud_clock: 'utc',
      pref_prompt_username: '',
      pref_compare_view_mode: 'auto',
      pref_compare_context: '3',
      pref_options_modal_last_tab: 'preferences',
      pref_tour_seen_version: '',
    };
  }

  function normalizeSessionPreferences(raw, defaults, { timestampModes = ['off', 'elapsed', 'clock'] } = {}) {
    const prefs = { ...(defaults || defaultSessionPreferences()) };
    const source = (raw && typeof raw === 'object') ? raw : {};
    if (typeof source.pref_theme_name === 'string' && source.pref_theme_name.trim()) {
      prefs.pref_theme_name = source.pref_theme_name.trim();
    }
    if (typeof source.pref_active_project_id === 'string' && /^prj_[0-9a-f]{16}$/.test(source.pref_active_project_id)) {
      prefs.pref_active_project_id = source.pref_active_project_id;
    }
    prefs.pref_timestamps = coerceTimestampMode(source.pref_timestamps, timestampModes);
    prefs.pref_line_numbers = coerceLineNumberMode(source.pref_line_numbers);
    prefs.pref_welcome_intro = coerceWelcomeIntroMode(source.pref_welcome_intro);
    prefs.pref_share_redaction_default = coerceShareRedactionDefaultMode(source.pref_share_redaction_default);
    prefs.pref_project_auto_link_external_runs = source.pref_project_auto_link_external_runs === 'off' ? 'off' : 'on';
    prefs.pref_run_notify = coerceRunNotifyMode(source.pref_run_notify);
    prefs.pref_hud_clock = coerceHudClockMode(source.pref_hud_clock);
    prefs.pref_prompt_username = normalizePromptUsername(source.pref_prompt_username);
    prefs.pref_compare_view_mode = coerceCompareViewMode(source.pref_compare_view_mode);
    prefs.pref_compare_context = coerceCompareContextMode(source.pref_compare_context);
    prefs.pref_options_modal_last_tab = coerceOptionsModalTab(source.pref_options_modal_last_tab);
    prefs.pref_tour_seen_version = coerceTourSeenVersion(source.pref_tour_seen_version);
    return prefs;
  }

  function sessionPreferenceCacheKey(sessionId = '') {
    return `session_pref_cache:${sessionId || ''}`;
  }

  global.DarklabPreferenceCore = Object.freeze({
    SESSION_PREFERENCE_KEYS,
    WELCOME_INTRO_MODES,
    SHARE_REDACTION_DEFAULT_MODES,
    HUD_CLOCK_MODES,
    COMPARE_VIEW_MODES,
    COMPARE_CONTEXT_MODES,
    OPTIONS_MODAL_TABS,
    coerceTimestampMode,
    coerceLineNumberMode,
    coerceWelcomeIntroMode,
    coerceShareRedactionDefaultMode,
    coerceRunNotifyMode,
    coerceHudClockMode,
    coerceCompareViewMode,
    coerceCompareContextMode,
    coerceOptionsModalTab,
    normalizePromptUsername,
    coerceTourSeenVersion,
    defaultSessionPreferences,
    normalizeSessionPreferences,
    sessionPreferenceCacheKey,
  });
})(typeof window !== 'undefined' ? window : globalThis);
