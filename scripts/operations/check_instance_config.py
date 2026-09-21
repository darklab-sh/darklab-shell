#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Validate process-supplied configuration without application startup."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

# Installed at /app/tools as well as scripts/operations in the source checkout.
SCRIPT = Path(__file__).resolve()
APP_ROOT = SCRIPT.parents[2] / "app" if SCRIPT.parent.name == "operations" else SCRIPT.parents[1]
sys.path.insert(0, str(APP_ROOT))

from config_builder import ConfigLoadError, build_config  # noqa: E402
from config_inputs import ConfigInputError, input_layers  # noqa: E402
from config_inspection import SCHEMA_VERSION, inspection_payload  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-yaml", type=Path, help="Candidate local YAML replacing the process's configured local overlay.")
    parser.add_argument("--json", action="store_true", help="Print versioned, redacted JSON.")
    parser.add_argument("--strict", action="store_true", help="Return failure when normalization warnings are present.")
    args = parser.parse_args(argv)
    try:
        result = build_config(input_layers(dict(os.environ), candidate=args.local_yaml), dict(os.environ))
        output = inspection_payload(result.config.model_dump(), result.provenance, result.warnings,
                                    observation={"kind": "fresh evaluation", "label": "Fresh evaluation of supplied inputs"})
        output["valid"] = True
        output["strict"] = args.strict
        status = 1 if args.strict and result.warnings else 0
    except (ConfigInputError, ConfigLoadError) as exc:
        # Never print exception text, raw YAML, paths, or unreviewed warning fields.
        output = {"schema_version": SCHEMA_VERSION, "valid": False,
                  "observation": {"kind": "fresh evaluation"},
                  "error": str(exc) if isinstance(exc, ConfigInputError) else "configuration_invalid"}
        if isinstance(exc, ConfigLoadError):
            from config_inspection import catalog  # noqa: PLC0415
            output["fields"] = sorted({extra["key"] for _, _, extra in getattr(exc, "events", ())
                                       if extra.get("key") in catalog()})
        status = 2
    if args.json:
        print(json.dumps(output, ensure_ascii=False))
    elif not output["valid"]:
        print("Configuration invalid: " + output["error"])
        for key in output.get("fields", []):
            print("  Check " + key)
    else:
        print("Fresh evaluation of supplied inputs — not a running worker snapshot.")
        print("Configuration valid" + (" with warnings." if output["warnings"] else "."))
        for warning in output["warnings"]:
            print(f"Warning: {warning['key']}: {warning['reason']}")
        for row in output["settings"]:
            shown = row["effective"]
            display = "Value withheld" if shown["mode"] == "withheld" else json.dumps(shown["value"], ensure_ascii=False)
            if shown["mode"] == "summary":
                display = f"{shown['summary']}: {display}"
            if shown["truncated"]:
                display += " [truncated]"
            print(f"{row['key']} = {display} ({row['source']['name']})")
        print("Host / Compose settings and other running processes are not observed.")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
