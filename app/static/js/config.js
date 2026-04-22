// ── Shared utility module ──
const DEFAULT_SHARE_REDACTION_RULES = [
  {
    label: 'bearer token',
    pattern: 'Authorization:\\s*Bearer\\s+\\S+',
    replacement: 'Authorization: Bearer [redacted]',
    flags: 'i',
  },
  {
    label: 'email address',
    pattern: '\\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,63}\\b',
    replacement: '[email-redacted]',
    flags: 'i',
  },
  {
    label: 'ipv4 address',
    pattern: '\\b(?:25[0-5]|2[0-4]\\d|1\\d\\d|[1-9]?\\d)(?:\\.(?:25[0-5]|2[0-4]\\d|1\\d\\d|[1-9]?\\d)){3}\\b',
    replacement: '[ip-redacted]',
    flags: '',
  },
  {
    label: 'ipv6 address',
    pattern: '\\b(?:[0-9A-F]{1,4}:){2,7}[0-9A-F]{1,4}\\b',
    replacement: '[ip-redacted]',
    flags: 'i',
  },
  {
    label: 'hostname',
    pattern: '(?<![@\\w-])(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\\.)+[A-Z]{2,63}(?![\\w-])',
    replacement: '[host-redacted]',
    flags: 'i',
  },
];

// Default values used until the /config endpoint responds.
// app.js overwrites APP_CONFIG with the server response on page load, but these
// defaults keep early-rendered helpers safe during bootstrap failures.
let APP_CONFIG = {
  version: '',
  app_name: 'darklab_shell',
  project_readme: 'https://gitlab.com/darklab.sh/darklab-shell',
  prompt_prefix: 'anon@darklab:~$',
  default_theme: 'darklab_obsidian.yaml',
  share_redaction_enabled: true,
  share_redaction_rules: DEFAULT_SHARE_REDACTION_RULES,
  motd: '',
  recent_commands_limit: 8,
  max_output_lines: 5000,
  max_tabs: 8,
  history_panel_limit: 50,
  command_timeout_seconds: 3600,
  welcome_char_ms: 18,
  welcome_jitter_ms: 12,
  welcome_post_cmd_ms: 650,
  welcome_inter_block_ms: 850,
  welcome_first_prompt_idle_ms: 1500,
  welcome_post_status_pause_ms: 500,
  welcome_sample_count: 5,
  welcome_status_labels: ['CONFIG', 'RUNNER', 'HISTORY', 'LIMITS', 'AUTOCOMPLETE'],
  welcome_hint_interval_ms: 4200,
  welcome_hint_rotations: 0,
  diag_enabled: false,
};
