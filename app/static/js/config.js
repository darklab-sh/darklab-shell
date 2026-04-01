// ── App config ──
// Default values used until the /config endpoint responds.
// app.js overwrites APP_CONFIG with the server response on page load.
let APP_CONFIG = {
  app_name: 'shell.darklab.sh',
  default_theme: 'dark',
  motd: '',
  recent_commands_limit: 8,
  max_output_lines: 2000,
  history_panel_limit: 50,
};
