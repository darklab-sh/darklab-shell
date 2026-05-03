// ── App preference pure helpers ───────────────────────────────────────────
// Loaded before app.js. Storage, cookies, and DOM sync stay in app.js; the
// supported values and snapshot normalization live here.
(function (global) {
  const SESSION_PREFERENCE_KEYS = Object.freeze([
    'pref_theme_name',
    'pref_timestamps',
    'pref_line_numbers',
    'pref_welcome_intro',
    'pref_share_redaction_default',
    'pref_run_notify',
    'pref_hud_clock',
  ]);
  const WELCOME_INTRO_MODES = Object.freeze(['animated', 'disable_animation', 'remove']);
  const SHARE_REDACTION_DEFAULT_MODES = Object.freeze(['unset', 'redacted', 'raw']);
  const HUD_CLOCK_MODES = Object.freeze(['utc', 'local']);

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

  function defaultSessionPreferences(defaultTheme = 'darklab_obsidian.yaml') {
    return {
      pref_theme_name: defaultTheme || 'darklab_obsidian.yaml',
      pref_timestamps: 'off',
      pref_line_numbers: 'off',
      pref_welcome_intro: 'animated',
      pref_share_redaction_default: 'unset',
      pref_run_notify: 'off',
      pref_hud_clock: 'utc',
    };
  }

  function normalizeSessionPreferences(raw, defaults, { timestampModes = ['off', 'elapsed', 'clock'] } = {}) {
    const prefs = { ...(defaults || defaultSessionPreferences()) };
    const source = (raw && typeof raw === 'object') ? raw : {};
    if (typeof source.pref_theme_name === 'string' && source.pref_theme_name.trim()) {
      prefs.pref_theme_name = source.pref_theme_name.trim();
    }
    prefs.pref_timestamps = coerceTimestampMode(source.pref_timestamps, timestampModes);
    prefs.pref_line_numbers = coerceLineNumberMode(source.pref_line_numbers);
    prefs.pref_welcome_intro = coerceWelcomeIntroMode(source.pref_welcome_intro);
    prefs.pref_share_redaction_default = coerceShareRedactionDefaultMode(source.pref_share_redaction_default);
    prefs.pref_run_notify = coerceRunNotifyMode(source.pref_run_notify);
    prefs.pref_hud_clock = coerceHudClockMode(source.pref_hud_clock);
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
    coerceTimestampMode,
    coerceLineNumberMode,
    coerceWelcomeIntroMode,
    coerceShareRedactionDefaultMode,
    coerceRunNotifyMode,
    coerceHudClockMode,
    defaultSessionPreferences,
    normalizeSessionPreferences,
    sessionPreferenceCacheKey,
  });
})(typeof window !== 'undefined' ? window : globalThis);
