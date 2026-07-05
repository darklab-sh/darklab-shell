"""Typed command-input and restricted-target helpers for command registry data."""

from __future__ import annotations

import ipaddress
from collections.abc import Callable
from urllib.parse import urlparse

from services.commands import registry_autocomplete
from services.commands.registry_loader import dedupe_preserve_order as _dedupe_preserve_order
from services.commands.registry_validation import split_command_argv

RESTRICTABLE_VALUE_TYPES = {"cidr", "domain", "host", "ip", "target", "url"}
PROJECT_TARGET_VALUE_TYPES = RESTRICTABLE_VALUE_TYPES | {"port_set"}


def value_type_is_restrictable(value_type: str) -> bool:
    return str(value_type or "").strip().lower() in RESTRICTABLE_VALUE_TYPES


def _dict_value(data: dict[str, object], key: str) -> dict:
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def _list_value(data: dict[str, object], key: str) -> list:
    value = data.get(key)
    return value if isinstance(value, list) else []


def autocomplete_value_type_from_hint(spec: dict[str, object], trigger: str) -> str:
    hints = _dict_value(spec, "arg_hints").get(trigger) or []
    for hint in hints:
        if not isinstance(hint, dict):
            continue
        value_type = str(hint.get("value_type") or "").strip().lower()
        if value_type:
            return value_type
    return ""


def autocomplete_flag_value_types(spec: dict[str, object]) -> dict[str, str]:
    value_types: dict[str, str] = {}
    for flag in _list_value(spec, "flags"):
        if not isinstance(flag, dict):
            continue
        token = str(flag.get("value") or "").strip()
        if not token:
            continue
        value_type = str(flag.get("value_type") or "").strip().lower()
        if not value_type:
            value_type = autocomplete_value_type_from_hint(spec, token)
        if value_type:
            value_types[token] = value_type
    for trigger in _dict_value(spec, "arg_hints"):
        token = str(trigger or "").strip()
        if token and token != "__positional__" and token not in value_types:
            value_type = autocomplete_value_type_from_hint(spec, token)
            if value_type:
                value_types[token] = value_type
    return value_types


def autocomplete_positional_value_types(spec: dict[str, object]) -> list[str]:
    value_types = []
    for hint in _dict_value(spec, "arg_hints").get("__positional__", []) or []:
        if not isinstance(hint, dict):
            continue
        value_type = str(hint.get("value_type") or "").strip().lower()
        if value_type_is_restrictable(value_type):
            value_types.append(value_type)
    return _dedupe_preserve_order(value_types)


def autocomplete_positional_project_target_value_types(spec: dict[str, object]) -> list[str]:
    value_types = []
    for hint in _dict_value(spec, "arg_hints").get("__positional__", []) or []:
        if not isinstance(hint, dict):
            continue
        value_type = str(hint.get("value_type") or "").strip().lower()
        if value_type in PROJECT_TARGET_VALUE_TYPES:
            value_types.append(value_type)
    return _dedupe_preserve_order(value_types)


def autocomplete_value_flag_types(spec: dict[str, object]) -> dict[str, str]:
    flags: dict[str, str] = {}
    for flag in _list_value(spec, "flags"):
        if not isinstance(flag, dict):
            continue
        token = str(flag.get("value") or "").strip()
        if token:
            flags[token] = str(flag.get("value_type") or "").strip().lower()
    for trigger in _dict_value(spec, "arg_hints"):
        token = str(trigger or "").strip()
        if token and token != "__positional__":
            flags[token] = flags.get(token) or autocomplete_value_type_from_hint(spec, token)
    return flags


def _autocomplete_hint_marks_target_list_file(hint: dict) -> bool:
    placeholder = str(hint.get("value") or hint.get("placeholder") or "").strip().lower()
    description = str(hint.get("description") or "").strip().lower()
    return "file" in placeholder or "file containing" in description or "one " in description and " per line" in description


def _autocomplete_project_target_flag_specs(spec: dict[str, object]) -> dict[str, dict[str, object]]:
    flags: dict[str, dict[str, object]] = {}
    for flag in _list_value(spec, "flags"):
        if not isinstance(flag, dict):
            continue
        token = str(flag.get("value") or "").strip()
        if not token:
            continue
        flags[token] = {
            "value_type": str(flag.get("value_type") or "").strip().lower(),
            "target_list_file": False,
        }
    for trigger, hints in _dict_value(spec, "arg_hints").items():
        token = str(trigger or "").strip()
        if not token or token == "__positional__":
            continue
        flag_spec = flags.setdefault(token, {"value_type": "", "target_list_file": False})
        for hint in hints if isinstance(hints, list) else []:
            if not isinstance(hint, dict):
                continue
            value_type = str(hint.get("value_type") or "").strip().lower()
            if value_type and not flag_spec.get("value_type"):
                flag_spec["value_type"] = value_type
            if value_type in PROJECT_TARGET_VALUE_TYPES and _autocomplete_hint_marks_target_list_file(hint):
                flag_spec["target_list_file"] = True
    return flags


def autocomplete_spec_needs_normalization(spec: dict[str, object]) -> bool:
    if "arg_hints" not in spec or "arguments" in spec:
        return True
    return any(
        isinstance(flag, dict) and ("takes_value" in flag or "value_hint" in flag)
        for flag in _list_value(spec, "flags")
    )


def autocomplete_spec_for_tokens(
    tokens: list[str],
    cfg: dict | None = None,
    *,
    load_autocomplete_context: Callable[[dict | None], dict],
) -> tuple[dict[str, object], int]:
    if not tokens:
        return {}, 1
    context = load_autocomplete_context(cfg)
    spec = context.get(tokens[0].lower()) or {}
    if isinstance(spec, dict) and autocomplete_spec_needs_normalization(spec):
        spec = registry_autocomplete._normalize_single_autocomplete_spec(spec)
    start_index = 1
    subcommands = spec.get("subcommands") if isinstance(spec, dict) else None
    if isinstance(subcommands, dict) and len(tokens) > 1:
        sub_spec = subcommands.get(tokens[1].lower())
        if isinstance(sub_spec, dict):
            if autocomplete_spec_needs_normalization(sub_spec):
                sub_spec = registry_autocomplete._normalize_single_autocomplete_spec(sub_spec, include_pipe=False)
            return sub_spec, 2
    return (spec if isinstance(spec, dict) else {}), start_index


def flag_value_from_token(tokens: list[str], index: int, flag: str) -> tuple[str | None, int | None]:
    token = tokens[index]
    if token == flag:
        if index + 1 >= len(tokens) or tokens[index + 1].startswith("-"):
            return None, None
        return tokens[index + 1], index + 1
    if flag.startswith("--") and token.startswith(f"{flag}="):
        return token[len(flag) + 1:], index
    if not flag.startswith("--") and token.startswith(flag) and token != flag:
        return token[len(flag):], index
    return None, None


def command_project_target_inputs(
    command: str,
    cfg: dict | None = None,
    *,
    load_autocomplete_context: Callable[[dict | None], dict],
) -> list[dict[str, str]]:
    """Return registry-typed command inputs that can become project targets."""
    tokens = split_command_argv(command)
    if not tokens:
        return []
    spec, start_index = autocomplete_spec_for_tokens(tokens, cfg=cfg, load_autocomplete_context=load_autocomplete_context)
    if not spec:
        return []
    flag_value_specs = _autocomplete_project_target_flag_specs(spec)
    positional_types = autocomplete_positional_project_target_value_types(spec)
    inputs = []
    consumed: set[int] = set(range(start_index))
    positional_index = 0

    index = start_index
    while index < len(tokens):
        token = tokens[index]
        matched_flag = ""
        matched_value = ""
        matched_value_index = index
        matched_value_type = ""
        matched_target_list_file = False
        for flag, flag_spec in flag_value_specs.items():
            value, value_index = flag_value_from_token(tokens, index, flag)
            if value is None or value_index is None:
                continue
            matched_flag = flag
            matched_value = value
            matched_value_index = value_index
            matched_value_type = str(flag_spec.get("value_type") or "")
            matched_target_list_file = bool(flag_spec.get("target_list_file"))
            break
        if matched_flag:
            consumed.add(index)
            consumed.add(matched_value_index)
            if matched_value_type in PROJECT_TARGET_VALUE_TYPES:
                inputs.append({
                    "value": str(matched_value or ""),
                    "value_type": matched_value_type,
                    "source_kind": "flag",
                    "source_name": matched_flag,
                    "target_list_file": "1" if matched_target_list_file else "",
                })
            index = matched_value_index + 1
            continue
        if token.startswith("-"):
            consumed.add(index)
            index += 1
            continue
        if index not in consumed and positional_types:
            value_type = positional_types[min(positional_index, len(positional_types) - 1)]
            positional_index += 1
            inputs.append({
                "value": token,
                "value_type": value_type,
                "source_kind": "positional",
                "source_name": f"argument_{positional_index}",
            })
        index += 1
    return inputs


def candidate_host_tokens(value: str) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    candidates = [raw.strip("[]")]
    if "://" in raw:
        parsed = urlparse(raw)
        if parsed.hostname:
            candidates.append(parsed.hostname)
    elif raw.startswith("//"):
        parsed = urlparse(f"scheme:{raw}")
        if parsed.hostname:
            candidates.append(parsed.hostname)
    if raw.startswith("[") and "]" in raw:
        candidates.append(raw[1:raw.index("]")])
    elif raw.count(":") == 1 and "/" not in raw:
        host, port = raw.rsplit(":", 1)
        if host and port.isdigit():
            candidates.append(host)
    return _dedupe_preserve_order([item.strip("[]") for item in candidates if item.strip("[]")])


def restricted_value_match(value: str, networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network]) -> str | None:
    if not networks:
        return None
    for candidate in candidate_host_tokens(value):
        try:
            if "/" in candidate:
                candidate_network = ipaddress.ip_network(candidate, strict=False)
                if any(candidate_network.overlaps(network) for network in networks):
                    return candidate
            else:
                candidate_ip = ipaddress.ip_address(candidate)
                if any(candidate_ip in network for network in networks):
                    return candidate
        except ValueError:
            continue
    return None


def restricted_input_reason(value: str) -> str:
    return f"Command input targets restricted IP/CIDR value: {value}"


def restricted_inline_input_reason(
    command: str,
    cfg: dict | None,
    *,
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network],
    load_autocomplete_context: Callable[[dict | None], dict],
) -> str:
    if not networks:
        return ""
    tokens = split_command_argv(command)
    if not tokens:
        return ""
    spec, start_index = autocomplete_spec_for_tokens(tokens, cfg=cfg, load_autocomplete_context=load_autocomplete_context)
    if not spec:
        return ""
    flag_value_types = autocomplete_flag_value_types(spec)
    positional_types = autocomplete_positional_value_types(spec)
    consumed: set[int] = set(range(start_index))
    positional_index = 0

    index = start_index
    while index < len(tokens):
        token = tokens[index]
        matched_flag = None
        matched_value_index = None
        for flag, value_type in flag_value_types.items():
            value, value_index = flag_value_from_token(tokens, index, flag)
            if value is None or value_index is None:
                continue
            matched_flag = flag
            matched_value_index = value_index
            if value_type_is_restrictable(value_type):
                blocked = restricted_value_match(value, networks)
                if blocked:
                    return restricted_input_reason(blocked)
            break
        if matched_flag is not None:
            consumed.add(index)
            if matched_value_index is not None:
                consumed.add(matched_value_index)
            index = (matched_value_index + 1) if matched_value_index is not None else index + 1
            continue
        if token.startswith("-"):
            consumed.add(index)
            index += 1
            continue
        if index not in consumed and positional_types:
            value_type = positional_types[min(positional_index, len(positional_types) - 1)]
            positional_index += 1
            if value_type_is_restrictable(value_type):
                blocked = restricted_value_match(token, networks)
                if blocked:
                    return restricted_input_reason(blocked)
        index += 1
    return ""
