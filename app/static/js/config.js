// ── App config ──
// Default values used until the /config endpoint responds.
// app.js overwrites APP_CONFIG with the server response on page load.
let APP_CONFIG = {
  version: '1.1',
  app_name: 'shell.darklab.sh',
  default_theme: 'dark',
  motd: '',
  recent_commands_limit: 8,
  max_output_lines: 2000,
  max_tabs: 8,
  history_panel_limit: 50,
  command_timeout_seconds: 0,
  welcome_char_ms: 10,
  welcome_jitter_ms: 10,
  welcome_post_cmd_ms: 700,
  welcome_inter_block_ms: 1500,
};
