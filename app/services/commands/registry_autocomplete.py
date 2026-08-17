# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Command autocomplete context normalization and feature filtering."""

from __future__ import annotations

from copy import deepcopy

from services.commands.features import (
    suggestion_enabled_for_features as _suggestion_enabled_for_features,
    suggestion_required_features as _suggestion_required_features,
)


def _coerce_positive_int(value: object, default: int) -> int:
    try:
        parsed = int(value) if not isinstance(value, bool) and isinstance(value, (int, float, str, bytes, bytearray)) else default
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _suggestion_interactive_enabled(item) -> bool:
    raw_interactive = item.get("interactive") if isinstance(item, dict) else None
    if isinstance(raw_interactive, str):
        return raw_interactive.strip().lower() in {"1", "true", "yes", "on"}
    return raw_interactive is True


def _normalize_context_suggestion(item):
    if isinstance(item, str):
        value = item.strip()
        return {"value": value, "description": ""} if value else None
    if not isinstance(item, dict):
        return None
    raw_value = item.get("value")
    if raw_value is None and item.get("placeholder") is not None:
        raw_value = item.get("placeholder")
    value = str(raw_value or "").strip()
    if not value:
        return None
    description = str(item.get("description", "")).strip()
    result: dict[str, object] = {"value": value, "description": description}
    # Insert text is whitespace-significant (e.g. "set " to leave the caret
    # past a trailing space), so only strip when the key is absent.
    raw_insert = item.get("insert")
    if raw_insert is not None:
        result["insertValue"] = str(raw_insert)
    raw_label = item.get("label")
    if raw_label is not None:
        label = str(raw_label).strip()
        if label:
            result["label"] = label
    if "hintOnly" in item or "hint_only" in item:
        raw_hint_only = item.get("hintOnly") if "hintOnly" in item else item.get("hint_only")
        result["hintOnly"] = bool(raw_hint_only)
    value_type = str(item.get("value_type") or item.get("value_kind") or item.get("type") or "").strip().lower()
    if value_type:
        result["value_type"] = value_type
    raw_target_types = item.get("target_types")
    if isinstance(raw_target_types, (list, tuple, set, frozenset)):
        target_types = [
            str(target_type or "").strip().lower()
            for target_type in raw_target_types
            if str(target_type or "").strip()
        ]
        if target_types:
            result["target_types"] = list(dict.fromkeys(target_types))
    raw_position = item.get("position") or item.get("order") or item.get("argument_position")
    raw_position = raw_position or item.get("argument_order")
    position = _coerce_positive_int(raw_position, 0)
    if position:
        result["position"] = position
    raw_wordlist_category = item.get("wordlist_category")
    if raw_wordlist_category:
        if isinstance(raw_wordlist_category, (list, tuple, set)):
            categories = [
                str(value).strip().lower()
                for value in raw_wordlist_category
                if str(value).strip()
            ]
            if categories:
                result["wordlist_category"] = categories
        else:
            category = str(raw_wordlist_category).strip().lower()
            if category:
                result["wordlist_category"] = category
    required_features = _suggestion_required_features(item)
    if required_features:
        result["feature_required"] = required_features if len(required_features) > 1 else required_features[0]
    smoke = _normalize_smoke_metadata(item.get("smoke"))
    if smoke is not None:
        result["smoke"] = smoke
    return result


def _normalize_smoke_metadata(raw_value):
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, str):
        profile = raw_value.strip().lower()
        return {"profile": profile} if profile else None
    if not isinstance(raw_value, dict):
        return None
    result = {}
    for key in ("profile", "purpose"):
        value = str(raw_value.get(key) or "").strip().lower()
        if value:
            result[key] = value
    if "enabled" in raw_value:
        result["enabled"] = bool(raw_value["enabled"])
    return result or None


def filter_autocomplete_context_by_features(context: dict, cfg=None) -> dict:
    filtered: dict[str, dict] = {}
    for root, raw_spec in (context or {}).items():
        if not isinstance(raw_spec, dict):
            continue
        spec = deepcopy(raw_spec)
        raw_flags = [item for item in spec.get("flags", []) or [] if isinstance(item, dict)]
        enabled_flags = [item for item in raw_flags if _suggestion_enabled_for_features(item, cfg)]
        disabled_flag_tokens = {
            str(item.get("value") or "")
            for item in raw_flags
            if item not in enabled_flags and item.get("value")
        }
        spec["flags"] = enabled_flags
        spec["expects_value"] = [
            token for token in spec.get("expects_value", []) or []
            if str(token) not in disabled_flag_tokens
        ]
        spec["arg_hints"] = {
            trigger: [
                item for item in hints or []
                if _suggestion_enabled_for_features(item, cfg)
            ]
            for trigger, hints in (spec.get("arg_hints") or {}).items()
            if str(trigger) not in disabled_flag_tokens
        }
        spec["examples"] = [
            item for item in spec.get("examples", []) or []
            if _suggestion_enabled_for_features(item, cfg)
        ]
        spec["sequence_arg_hints"] = {
            trigger: [
                item for item in hints or []
                if _suggestion_enabled_for_features(item, cfg)
            ]
            for trigger, hints in (spec.get("sequence_arg_hints") or {}).items()
        }
        filtered_subcommands = {}
        for name, raw_sub_spec in (spec.get("subcommands") or {}).items():
            if not isinstance(raw_sub_spec, dict):
                continue
            sub_spec = deepcopy(raw_sub_spec)
            sub_raw_flags = [item for item in sub_spec.get("flags", []) or [] if isinstance(item, dict)]
            sub_enabled_flags = [item for item in sub_raw_flags if _suggestion_enabled_for_features(item, cfg)]
            sub_disabled_flag_tokens = {
                str(item.get("value") or "")
                for item in sub_raw_flags
                if item not in sub_enabled_flags and item.get("value")
            }
            sub_spec["flags"] = sub_enabled_flags
            sub_spec["expects_value"] = [
                token for token in sub_spec.get("expects_value", []) or []
                if str(token) not in sub_disabled_flag_tokens
            ]
            sub_spec["arg_hints"] = {
                trigger: [
                    item for item in hints or []
                    if _suggestion_enabled_for_features(item, cfg)
                ]
                for trigger, hints in (sub_spec.get("arg_hints") or {}).items()
                if str(trigger) not in sub_disabled_flag_tokens
            }
            sub_spec["examples"] = [
                item for item in sub_spec.get("examples", []) or []
                if _suggestion_enabled_for_features(item, cfg)
            ]
            sub_spec["sequence_arg_hints"] = {
                trigger: [
                    item for item in hints or []
                    if _suggestion_enabled_for_features(item, cfg)
                ]
                for trigger, hints in (sub_spec.get("sequence_arg_hints") or {}).items()
            }
            filtered_subcommands[name] = sub_spec
        spec["subcommands"] = filtered_subcommands
        filtered[root] = spec
    return filtered


def _append_unique_context_token(bucket, seen, raw_token):
    token = str(raw_token or "").strip()
    if not token:
        return
    key = token
    if key in seen:
        return
    seen.add(key)
    bucket.append(token)


def _append_unique_context_suggestions(bucket, seen, raw_items):
    for raw_item in raw_items or []:
        hint = _normalize_context_suggestion(raw_item)
        if not hint:
            continue
        key = str(hint["value"]).lower()
        if key in seen:
            continue
        seen.add(key)
        bucket.append(hint)


def _normalize_single_autocomplete_spec(raw_spec: dict, *, include_pipe: bool = True) -> dict:
    flags = []
    seen_flags = set()
    for raw_flag in raw_spec.get("flags", []) or []:
        flag = _normalize_context_suggestion(raw_flag)
        if not flag:
            continue
        key = str(flag["value"])
        if key in seen_flags:
            continue
        seen_flags.add(key)
        flags.append(flag)

    expects_value = []
    seen_value_flags = set()

    arg_hints = {}

    def _hint_bucket(trigger):
        bucket = arg_hints.setdefault(trigger, [])
        seen = {str(item.get("value", "")) for item in bucket if isinstance(item, dict)}
        return bucket, seen

    for raw_flag in raw_spec.get("flags", []) or []:
        if not isinstance(raw_flag, dict):
            continue
        token = str(raw_flag.get("value") or "").strip()
        if not token:
            continue
        flag_value_type = str(
            raw_flag.get("value_type")
            or raw_flag.get("value_kind")
            or raw_flag.get("type")
            or ""
        ).strip().lower()
        if raw_flag.get("takes_value"):
            _append_unique_context_token(expects_value, seen_value_flags, token)
        if raw_flag.get("closes"):
            arg_hints.setdefault(token, [])
        hint_sources = []
        raw_value_hint = raw_flag.get("value_hint")
        if raw_value_hint is not None:
            hint_sources.extend(raw_value_hint if isinstance(raw_value_hint, list) else [raw_value_hint])
        if raw_flag.get("suggest") is not None:
            hint_sources.extend(raw_flag.get("suggest") or [])
        if flag_value_type and not hint_sources:
            hint_sources.append({
                "placeholder": f"<{flag_value_type}>",
                "description": str(raw_flag.get("description") or "").strip(),
                "value_type": flag_value_type,
            })
        if hint_sources:
            bucket, seen = _hint_bucket(token)
            if flag_value_type:
                enriched_sources = []
                for source in hint_sources:
                    if isinstance(source, dict):
                        enriched = dict(source)
                        enriched.setdefault("value_type", flag_value_type)
                        if raw_flag.get("wordlist_category") and "wordlist_category" not in enriched:
                            enriched["wordlist_category"] = raw_flag.get("wordlist_category")
                        enriched_sources.append(enriched)
                    else:
                        enriched_sources.append(source)
                hint_sources = enriched_sources
            _append_unique_context_suggestions(bucket, seen, hint_sources)

    positional_bucket, positional_seen = _hint_bucket("__positional__")
    _append_unique_context_suggestions(
        positional_bucket,
        positional_seen,
        raw_spec.get("arguments") or [],
    )

    raw_subcommands = raw_spec.get("subcommands")
    subcommand_specs = {}
    if isinstance(raw_subcommands, dict):
        for raw_name, raw_sub_spec in raw_subcommands.items():
            name = str(raw_name or "").strip().lower()
            if not name or not isinstance(raw_sub_spec, dict):
                continue
            description = str(raw_sub_spec.get("description") or "").strip()
            nested = _normalize_single_autocomplete_spec(raw_sub_spec, include_pipe=False)
            if description:
                nested["description"] = description
            subcommand_specs[name] = nested
            display = {
                "value": name,
                "description": description,
                "insert": raw_sub_spec.get("insert", f"{name} "),
            }
            normalized_sub = _normalize_context_suggestion(display)
            if normalized_sub:
                key = str(normalized_sub["value"])
                if key not in positional_seen:
                    positional_seen.add(key)
                    positional_bucket.append(normalized_sub)
    else:
        for raw_sub in raw_subcommands or []:
            if not isinstance(raw_sub, dict):
                continue
            token = str(raw_sub.get("value") or "").strip()
            if not token:
                continue
            if raw_sub.get("takes_value"):
                _append_unique_context_token(expects_value, seen_value_flags, token)
            if raw_sub.get("closes"):
                arg_hints.setdefault(token, [])

            hint_sources = []
            raw_value_hint = raw_sub.get("value_hint")
            if raw_value_hint is not None:
                hint_sources.extend(raw_value_hint if isinstance(raw_value_hint, list) else [raw_value_hint])
            if raw_sub.get("suggest") is not None:
                hint_sources.extend(raw_sub.get("suggest") or [])
            if hint_sources:
                bucket, seen = _hint_bucket(token)
                _append_unique_context_suggestions(bucket, seen, hint_sources)

            subcommand_display = {
                "value": token,
                "description": str(raw_sub.get("description", "")).strip(),
            }
            if raw_sub.get("takes_value"):
                placeholder = None
                if isinstance(raw_value_hint, dict):
                    placeholder = raw_value_hint.get("placeholder") or raw_value_hint.get("value")
                elif isinstance(raw_value_hint, list) and raw_value_hint:
                    first_hint = raw_value_hint[0]
                    if isinstance(first_hint, dict):
                        placeholder = first_hint.get("placeholder") or first_hint.get("value")
                if placeholder:
                    subcommand_display["value"] = f"{token} {str(placeholder).strip()}"
                raw_insert = raw_sub.get("insert")
                subcommand_display["insert"] = str(raw_insert) if raw_insert is not None else f"{token} "
            else:
                raw_insert = raw_sub.get("insert")
                if raw_insert is not None:
                    subcommand_display["insert"] = str(raw_insert)
            normalized_sub = _normalize_context_suggestion(subcommand_display)
            if normalized_sub and not raw_sub.get("hidden"):
                key = str(normalized_sub["value"]).lower()
                if key not in positional_seen:
                    positional_seen.add(key)
                    positional_bucket.append(normalized_sub)

    raw_argument_limit = raw_spec.get("argument_limit")
    argument_limit = raw_argument_limit if isinstance(raw_argument_limit, int) and raw_argument_limit > 0 else None

    sequence_arg_hints = {}
    for trigger, hints in (raw_spec.get("sequence_arg_hints") or {}).items():
        bucket = []
        seen = set()
        _append_unique_context_suggestions(bucket, seen, hints)
        sequence_arg_hints[str(trigger or "").strip().lower()] = bucket

    close_after = {}
    raw_close_after = raw_spec.get("close_after")
    if isinstance(raw_close_after, dict):
        for raw_token, raw_limit in raw_close_after.items():
            token = str(raw_token or "").strip().lower()
            if not token:
                continue
            try:
                limit = int(raw_limit)
            except (TypeError, ValueError):
                continue
            if limit >= 0:
                close_after[token] = limit

    raw_pipe_spec = raw_spec.get("pipe")
    pipe_spec: dict[str, object] = raw_pipe_spec if include_pipe and isinstance(raw_pipe_spec, dict) else {}
    pipe_command = bool(pipe_spec.get("enabled"))
    pipe_insert_value = str(pipe_spec.get("insert") or "").strip()
    pipe_label = str(pipe_spec.get("label") or "").strip() or pipe_insert_value
    pipe_description = str(pipe_spec.get("description") or "").strip()

    examples = []
    seen_examples = set()
    for raw_ex in raw_spec.get("examples", []) or []:
        ex = _normalize_context_suggestion(raw_ex)
        if not ex:
            continue
        key = str(ex["value"]).lower()
        if key in seen_examples:
            continue
        seen_examples.add(key)
        examples.append(ex)

    return {
        "flags": flags,
        "expects_value": expects_value,
        "arg_hints": arg_hints,
        "sequence_arg_hints": sequence_arg_hints,
        "close_after": close_after,
        "subcommands": subcommand_specs,
        "argument_limit": argument_limit,
        "pipe_command": pipe_command,
        "pipe_insert_value": pipe_insert_value,
        "pipe_label": pipe_label,
        "pipe_description": pipe_description,
        "examples": examples,
    }


def _normalize_autocomplete_context(data):
    if not isinstance(data, dict):
        return {}
    normalized = {}
    for raw_root, raw_spec in data.items():
        root = str(raw_root or "").strip().lower()
        if not root or not isinstance(raw_spec, dict):
            continue
        normalized[root] = _normalize_single_autocomplete_spec(raw_spec)
    return normalized


def normalize_autocomplete_spec(root: str, raw_spec: object) -> dict:
    """Normalize one command's declarative autocomplete grammar."""
    normalized_root = str(root or "").strip().lower()
    if not normalized_root or not isinstance(raw_spec, dict) or not raw_spec:
        return {}
    return _normalize_autocomplete_context({
        normalized_root: raw_spec,
    }).get(normalized_root, {})


def _merge_autocomplete_context(base, overlay):
    merged = deepcopy(base if isinstance(base, dict) else {})
    for root, spec in (overlay or {}).items():
        if not isinstance(spec, dict):
            continue
        current = merged.setdefault(root, {
            "flags": [],
            "expects_value": [],
            "arg_hints": {},
            "sequence_arg_hints": {},
            "close_after": {},
            "subcommands": {},
            "argument_limit": None,
            "pipe_command": False,
            "pipe_insert_value": "",
            "pipe_label": "",
            "pipe_description": "",
            "examples": [],
        })

        if isinstance(spec.get("argument_limit"), int) and spec["argument_limit"] > 0:
            current["argument_limit"] = spec["argument_limit"]

        if spec.get("description"):
            current["description"] = spec["description"]
        if spec.get("feature_required"):
            current["feature_required"] = spec["feature_required"]

        if spec.get("pipe_command"):
            current["pipe_command"] = True
        if spec.get("pipe_insert_value"):
            current["pipe_insert_value"] = spec["pipe_insert_value"]
        if spec.get("pipe_label"):
            current["pipe_label"] = spec["pipe_label"]
        if spec.get("pipe_description"):
            current["pipe_description"] = spec["pipe_description"]
        if not current.get("pipe_label") and current.get("pipe_insert_value"):
            current["pipe_label"] = current["pipe_insert_value"]

        seen_flags = {str(item["value"]) for item in current.get("flags", []) if isinstance(item, dict)}
        for flag in spec.get("flags", []) or []:
            key = str(flag["value"])
            if key in seen_flags:
                continue
            seen_flags.add(key)
            current.setdefault("flags", []).append(flag)

        seen_value_flags = {str(item) for item in current.get("expects_value", [])}
        for token in spec.get("expects_value", []) or []:
            key = str(token)
            if key in seen_value_flags:
                continue
            seen_value_flags.add(key)
            current.setdefault("expects_value", []).append(token)

        for trigger, hints in (spec.get("arg_hints", {}) or {}).items():
            bucket = current.setdefault("arg_hints", {}).setdefault(trigger, [])
            seen_hints = {item["value"].lower() for item in bucket if isinstance(item, dict)}
            for hint in hints or []:
                key = hint["value"].lower()
                if key in seen_hints:
                    continue
                seen_hints.add(key)
                bucket.append(hint)

        for trigger, hints in (spec.get("sequence_arg_hints", {}) or {}).items():
            bucket = current.setdefault("sequence_arg_hints", {}).setdefault(trigger, [])
            seen_hints = {item["value"].lower() for item in bucket if isinstance(item, dict)}
            for hint in hints or []:
                key = hint["value"].lower()
                if key in seen_hints:
                    continue
                seen_hints.add(key)
                bucket.append(hint)

        current.setdefault("close_after", {}).update(spec.get("close_after") or {})

        current_subcommands = current.setdefault("subcommands", {})
        for name, sub_spec in (spec.get("subcommands") or {}).items():
            if not isinstance(sub_spec, dict):
                continue
            sub_name = str(name or "").strip().lower()
            if not sub_name:
                continue
            if sub_name not in current_subcommands:
                current_subcommands[sub_name] = deepcopy(sub_spec)
                continue
            merged_sub = _merge_autocomplete_context(
                {sub_name: current_subcommands[sub_name]},
                {sub_name: sub_spec},
            )
            current_subcommands[sub_name] = merged_sub[sub_name]

        seen_examples = {item["value"].lower() for item in current.get("examples", []) if isinstance(item, dict)}
        for ex in spec.get("examples", []) or []:
            key = str(ex["value"]).lower()
            if key in seen_examples:
                continue
            seen_examples.add(key)
            current.setdefault("examples", []).append(ex)
    return merged
