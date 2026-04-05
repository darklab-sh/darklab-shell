// ── App config ──
// Default values used until the /config endpoint responds.
// app.js overwrites APP_CONFIG with the server response on page load.
let APP_CONFIG = {
  version: '1.2',
  app_name: 'shell.darklab.sh',
  default_theme: 'dark',
  motd: '',
  recent_commands_limit: 8,
  max_output_lines: 2000,
  max_tabs: 8,
  history_panel_limit: 50,
  command_timeout_seconds: 3600,
  welcome_char_ms: 18,
  welcome_jitter_ms: 12,
  welcome_post_cmd_ms: 650,
  welcome_inter_block_ms: 850,
  welcome_first_prompt_idle_ms: 2100,
  welcome_post_status_pause_ms: 220,
  welcome_sample_count: 5,
  welcome_status_labels: ['CONFIG', 'RUNNER', 'HISTORY', 'LIMITS', 'AUTOCOMPLETE'],
  welcome_hint_interval_ms: 4200,
  welcome_hint_rotations: 2,
};
