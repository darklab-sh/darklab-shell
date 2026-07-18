#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Generate the checked-in API v1 OpenAPI contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.api_v1.openapi import openapi_spec  # noqa: E402


def main() -> int:
    target = ROOT / "docs" / "api-v1-openapi.json"
    target.write_text(json.dumps(openapi_spec(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
