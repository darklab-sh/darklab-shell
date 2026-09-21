# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Catalog-controlled configuration disclosure shared by web and local tools."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from config_builder import (
    ACCESS_PROFILES, AUDIT_EXPORT_MAX_ROWS, DURATION_BOUNDS, ENVIRONMENT_KEYS,
    OIDC_PROVISIONING_POLICIES, _FORGIVING_BOOL_KEYS, _FORGIVING_INT_DEFAULTS,
    _FORGIVING_MB_KEYS, build_config,
)

SCHEMA_VERSION = 1
MAX_VALUE_CHARS = 4096
MAX_LIST_ITEMS = 64
MAX_WARNINGS = 100
DERIVED_SUMMARIES = {
    "custom_redaction_rule_count": ("share_redaction_rules", "count"),
    "ai_base_url_configured": ("ai_base_url", "presence"),
}


@lru_cache(maxsize=1)
def catalog() -> dict[str, dict[str, Any]]:
    return json.loads(Path(__file__).with_name("config_catalog_data.json").read_text(encoding="utf-8"))


def field_values(data, prefix=""):
    result = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        result[path] = value
        if isinstance(value, dict):
            result.update(field_values(value, path))
    return result


def schema_fields(schema):
    result = {}

    def walk(node, prefix=""):
        if "$ref" in node:
            node = schema["$defs"][node["$ref"].rsplit("/", 1)[-1]]
        for key, value in node.get("properties", {}).items():
            path = f"{prefix}.{key}" if prefix else key
            result[path] = value
            walk(value, path)
    walk(schema)
    return result


def declared_rules(key, schema):
    rules = {name: schema[name] for name in ("type", "minimum", "maximum", "enum", "pattern") if name in schema}
    if key in DURATION_BOUNDS:
        rules.update(minimum=DURATION_BOUNDS[key][0], maximum=DURATION_BOUNDS[key][1], input="integer; invalid values rejected")
    elif key in _FORGIVING_INT_DEFAULTS:
        fallback, minimum = _FORGIVING_INT_DEFAULTS[key]
        rules.update(minimum=minimum, fallback=fallback,
                     input="numeric strings accepted; invalid values default; low values clamp")
        if key == "audit_export_max_rows":
            rules["maximum"] = AUDIT_EXPORT_MAX_ROWS
    elif key in _FORGIVING_BOOL_KEYS:
        rules["input"] = "boolean or 1/0, true/false, yes/no, on/off; invalid values default"
    elif key in _FORGIVING_MB_KEYS:
        rules["input"] = "numeric values or MB/m strings; negative values clamp to zero; invalid values default"
    if key == "access_profile":
        rules["enum"] = list(ACCESS_PROFILES)
    elif key == "oidc_provisioning":
        rules["enum"] = list(OIDC_PROVISIONING_POLICIES)
    return rules


def safe_value(key, value, *, entries=None):
    """Only explicitly reviewed scalar/list or declared summary values may leave."""
    entry = (catalog() if entries is None else entries).get(key, {})
    mode = entry.get("disclosure")
    result = {"mode": "withheld", "value": None, "truncated": False}
    if entry.get("reviewed") is not True:
        return result
    if mode == "summary":
        form = entry.get("summary")
        if form == "count" and isinstance(value, (list, tuple)):
            return {"mode": "summary", "summary": "count", "value": len(value), "truncated": False}
        if form == "presence" and (value is None or isinstance(value, (str, bool, int, float))):
            return {"mode": "summary", "summary": "presence", "value": bool(value), "truncated": False}
        return result
    if mode != "full" or isinstance(value, dict):
        return result
    if isinstance(value, (list, tuple)):
        if any(not isinstance(item, (str, bool, int, float, type(None))) for item in value):
            return result
        items = [safe_value(key, item, entries=entries) for item in value[:MAX_LIST_ITEMS]]
        if any(item["mode"] != "full" for item in items):
            return result
        bounded = [item["value"] for item in items]
        truncated = len(value) > MAX_LIST_ITEMS or any(isinstance(item, str) and len(item) > MAX_VALUE_CHARS for item in value)
        # A budget for the complete list prevents many large entries multiplying payload size.
        while len(json.dumps(bounded)) > MAX_VALUE_CHARS and bounded:
            bounded.pop()
            truncated = True
        return {"mode": "full", "value": bounded, "truncated": truncated}
    if isinstance(value, str):
        # Even a full-value field cannot disclose URL userinfo accidentally.
        if "://" in value and "@" in value:
            return result
        return {"mode": "full", "value": value[:MAX_VALUE_CHARS], "truncated": len(value) > MAX_VALUE_CHARS}
    if value is None or isinstance(value, (bool, int, float)):
        return {"mode": "full", "value": value, "truncated": False}
    return result


def safe_warnings(warnings):
    entries = catalog()
    return [{"key": item.get("key") if item.get("key") in entries else "unknown input key",
             "event": item.get("event") if item.get("event") in {
                 "APP_NAME_TRUNCATED", "CONFIG_VALUE_DROPPED", "CONFIG_VALUE_DEFAULTED", "CONFIG_VALUE_CLAMPED",
                 "CONFIG_ALIAS_DEPRECATED"
             } else "CONFIG_INPUT_WARNING",
             "reason": item.get("reason") if item.get("reason") in {
                 "above_maximum_chars", "invalid_cidr", "invalid_domain_suffix", "invalid_int", "invalid_bool",
                 "invalid_redaction_rule", "below_minimum", "above_maximum", "below_database_pool_min", "invalid_mb",
                 "deprecated_alias"
             } else "input ignored or normalized"}
            for item in warnings[:MAX_WARNINGS]]


def source_details(source):
    if source == "built-in defaults":
        return {"layer": "default", "name": "Built-in default"}
    if source in ENVIRONMENT_KEYS:
        return {"layer": "environment", "name": source}
    if source == "local YAML" or str(source).endswith("config.local.yaml"):
        return {"layer": "local", "name": "Local YAML"}
    return {"layer": "shipped", "name": "Shipped YAML"}


def inspection_payload(values, provenance, warnings=(), *, observation=None):
    defaults = build_config().config
    default_values = field_values(defaults.model_dump())
    schemas = schema_fields(defaults.model_json_schema())
    diagnostics = safe_warnings(warnings)
    rows = []
    current_values = field_values(values)
    for key in schemas:
        value = current_values.get(key)
        entry = catalog().get(key, {})
        rows.append({
            "key": key, "label": entry.get("label", key), "group": entry.get("group", "Unclassified"),
            "description": entry.get("description", "Display metadata has not been reviewed."),
            "effective": safe_value(key, value), "default": safe_value(key, default_values.get(key)),
            "source": source_details(provenance.get(key, "built-in defaults")),
            "yaml": entry.get("yaml", ""), "environment": entry.get("environment", []),
            "processes": entry.get("processes", []), "apply": entry.get("apply", "Apply behavior unavailable."),
            "rules": declared_rules(key, schemas.get(key, {})),
            "warnings": [item for item in diagnostics if item["key"] == key],
        })
    host = json.loads(Path(__file__).with_name("config_host_catalog.json").read_text(encoding="utf-8"))
    return {"schema_version": SCHEMA_VERSION, "observation": observation or {"kind": "fresh evaluation"},
            "settings": rows, "warnings": diagnostics, "warnings_truncated": len(warnings) > MAX_WARNINGS,
            "host_settings": host}


def catalog_errors():
    cfg = build_config().config
    fields = field_values(cfg.model_dump())
    entries = catalog()
    errors = [f"missing:{key}" for key in fields.keys() - entries.keys()]
    errors += [f"stale:{key}" for key in entries.keys() - fields.keys()]
    for key, entry in entries.items():
        if not all(entry.get(field) for field in ("reviewed", "label", "group", "description", "yaml", "processes", "apply")):
            errors.append(f"incomplete:{key}")
        if entry.get("disclosure") not in {"full", "summary", "withheld"}:
            errors.append(f"disclosure:{key}")
        if entry.get("disclosure") == "summary" and entry.get("summary") not in {"count", "presence"}:
            errors.append(f"summary:{key}")
        if entry.get("environment") != [name for name, field in ENVIRONMENT_KEYS.items() if field == key]:
            errors.append(f"environment:{key}")
    return errors


def diagnostic_values(values, config):
    """Keep diagnostics' existing key set and scalar/list shape, using shared policy."""
    formatted = {}
    truncated = []
    withheld = []
    for key, value in values.items():
        source = DERIVED_SUMMARIES.get(key, (key, ""))[0]
        disclosed = safe_value(source, config.get(source) if key in DERIVED_SUMMARIES else value)
        formatted[key] = disclosed["value"]
        if disclosed["truncated"]:
            truncated.append(key)
        if disclosed["mode"] == "withheld":
            withheld.append(key)
    return formatted, truncated, withheld
