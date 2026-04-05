"""
Application configuration and scanner-user setup.
Imported by database, process, permalinks, and app modules.
"""

import os
import pwd
import yaml


def load_config():
    """Load config.yaml, falling back to defaults for any missing keys."""
    defaults = {
        "app_name":                   "shell.darklab.sh",
        "motd":                       "",
        "default_theme":              "dark",
        "history_panel_limit":        50,
        "recent_commands_limit":      8,
        "permalink_retention_days":   365,
        "log_level":                  "INFO",
        "log_format":                 "text",
        "rate_limit_per_minute":      30,
        "rate_limit_per_second":      5,
        "max_output_lines":           2000,
        "persist_full_run_output":    True,
        "full_output_max_bytes":      5 * 1024 * 1024,
        "max_tabs":                   8,
        "command_timeout_seconds":    0,
        "heartbeat_interval_seconds": 20,
        "welcome_char_ms":            18,
        "welcome_jitter_ms":          12,
        "welcome_post_cmd_ms":        650,
        "welcome_inter_block_ms":     850,
        "welcome_first_prompt_idle_ms": 1500,
        "welcome_post_status_pause_ms": 500,
        "welcome_sample_count":       5,
        "welcome_status_labels":      ["CONFIG", "RUNNER", "HISTORY", "LIMITS", "AUTOCOMPLETE"],
        "welcome_hint_interval_ms":   4200,
        "welcome_hint_rotations":     2,
    }
    config_path = os.path.join(os.path.dirname(__file__), "conf", "config.yaml")
    if os.path.exists(config_path):
        with open(config_path) as f:
            user_config = yaml.safe_load(f) or {}
        defaults.update(user_config)
    return defaults


CFG = load_config()

# Scanner user wrapping — prepend sudo -u scanner to run commands as the
# unprivileged scanner user. appuser (Gunicorn) is granted NOPASSWD sudo
# rights to scanner in /etc/sudoers. Falls back to running directly if
# sudo/scanner aren't available (local dev).
SCANNER_PREFIX = []
try:
    pwd.getpwnam("scanner")
    # Pass HOME=/tmp explicitly so nuclei (and other tools) use the tmpfs mount
    # for config/cache instead of /home/scanner which doesn't exist on the
    # read-only filesystem.
    SCANNER_PREFIX = ["sudo", "-u", "scanner", "env", "HOME=/tmp"]
except KeyError:
    pass  # scanner user doesn't exist — local dev, run directly
