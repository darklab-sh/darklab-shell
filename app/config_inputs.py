# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Read known configuration layers without importing the startup facade."""

from pathlib import Path

import yaml


class ConfigInputError(ValueError):
    """Input could not be read safely; the code contains no input contents."""


def read_yaml(path, *, required=False):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        if not required:
            return {}
        raise ConfigInputError("input_not_found") from None
    except (OSError, UnicodeError):
        raise ConfigInputError("input_unreadable") from None
    try:
        value = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        raise ConfigInputError("invalid_yaml") from None
    if not isinstance(value, dict):
        raise ConfigInputError("mapping_required")
    return value


def input_layers(environment, *, candidate=None):
    shipped = Path(environment.get("APP_CONF_DIR") or Path(__file__).parent / "conf")
    local = Path(environment.get("APP_LOCAL_CONF_DIR") or shipped)
    return [("shipped YAML", read_yaml(shipped / "config.yaml")),
            ("local YAML", read_yaml(candidate or local / "config.local.yaml", required=candidate is not None))]
