# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared destructive confirmation behavior for CLI commands."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any

from ..client import print_json


def destructive_action_confirmed(
    preview: Any,
    *,
    confirmed: bool,
    output_format: str,
    action: str,
    render_text: Callable[[Any], None],
) -> bool:
    """Show a server-owned preview and return whether mutation may continue."""
    if output_format == "json":
        if confirmed:
            print(json.dumps(preview, indent=2, sort_keys=True), file=sys.stderr)
        else:
            print_json(preview)
    else:
        render_text(preview)
    if confirmed:
        return True
    if output_format != "json":
        print(f"Preview only. Re-run with --confirm to {action}.")
    return False


__all__ = ["destructive_action_confirmed"]
