"""Validation helpers for AI-suggested next commands."""

from __future__ import annotations

from collections import Counter
from functools import lru_cache
import ipaddress
import logging
from pathlib import Path
import re
import shlex
from typing import Any
from urllib.parse import urlparse
import unicodedata

from config import CFG, get_share_redaction_rules
from core.helpers import get_log_session_id
from core.output_signals import command_root as output_command_root
from core.output_signals import extract_target
from core.redaction import REDACTED_ENTITY_SENTINEL
from services import metrics as app_metrics
from services.commands.registry import (
    load_autocomplete_context_from_commands_registry,
    required_secrets_for_command,
    validate_command,
)
from services.commands.wordlists import load_wordlist_catalog
from services.secrets.storage import get_secret_value_for_env
from services.secrets.vault import MasterKeyError, SecretDecryptError

NETWORK_TARGET_ROOTS = frozenset({
    "assetfinder",
    "curl",
    "dig",
    "ffuf",
    "feroxbuster",
    "gobuster",
    "host",
    "httpx",
    "ipinfo",
    "katana",
    "naabu",
    "nc",
    "nikto",
    "nmap",
    "nslookup",
    "nuclei",
    "openssl",
    "rustscan",
    "shodan",
    "sslscan",
    "sslyze",
    "testssl",
    "wafw00f",
    "wget",
})

NO_TARGET_ALLOWLIST = frozenset({
    "faq",
    "help",
    "history",
    "jobs",
    "providers",
    "secret",
    "tour",
    "wordlist",
})

_OPEN_PORT_RE = re.compile(r"\b(?P<port>\d{1,5})/(?P<proto>tcp|udp)\s+(?:open(?:\S*)?|is\s+open)\b", re.I)
_DISCOVERED_OPEN_PORT_RE = re.compile(
    r"\bDiscovered\s+open\s+port\s+(?P<port>\d{1,5})/(?P<proto>tcp|udp)\b",
    re.I,
)
_NMAP_PORT_FLAGS = frozenset({"-p", "--ports"})
_KNOWN_INVALID_FLAGS = {
    "testssl": frozenset({"-u"}),
}
_FALLBACK_WORDLIST_FLAGS_BY_ROOT = {
    "dnsrecon": {"-D": {"dns"}},
    "dnsx": {"-w": {"dns"}},
    "ffuf": {"-w": {"api", "cms", "web-content"}},
    "feroxbuster": {"-w": {"web-content"}, "--wordlist": {"web-content"}},
    "gobuster": {"-w": {"web-content"}},
}
_DUPLICATE_SOURCE_ROOTS = frozenset({"ffuf", "feroxbuster", "gobuster", "naabu", "nmap", "rustscan"})
_SOURCE_TARGET_RE = re.compile(r"(?<![A-Za-z0-9_-])SOURCE_TARGET(?![A-Za-z0-9_-])")
_TARGET_REDACTION_MARKERS = frozenset({
    "[host-redacted]",
    "[ip-redacted]",
    "[url-redacted]",
    "host-redacted",
    "ip-redacted",
    "url-redacted",
})
_TARGET_REDACTION_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?:"
    + "|".join(re.escape(marker) for marker in sorted(_TARGET_REDACTION_MARKERS))
    + r")(?![A-Za-z0-9_-])"
)

log = logging.getLogger("shell")
_UNRESOLVED_TARGET_DISPLAY = "[target-unresolved]"


def validate_suggestions(
    payload: dict[str, Any],
    *,
    context: dict[str, Any],
    session_id: str,
    project_target_snapshot: list[dict[str, Any]] | None = None,
    cfg: dict | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return payload with validation fields plus rows for the audit table."""
    active_cfg = CFG if cfg is None else cfg
    project_targets = project_target_snapshot or []
    trusted_targets = _trusted_targets(context, project_targets)
    source_targets = _source_targets(context, project_targets)
    source_fingerprint = _source_command_fingerprint(context, source_targets)
    known_ports = known_open_ports(context)
    seen_commands: set[str] = set()
    accepted_suggestions: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []

    for item in payload.get("suggestions") or []:
        if not isinstance(item, dict):
            continue
        result = _validate_one(
            item,
            trusted_targets=trusted_targets,
            source_targets=source_targets,
            source_fingerprint=source_fingerprint,
            known_ports=known_ports,
            session_id=session_id,
            cfg=active_cfg,
        )
        normalized_key = result["normalized_command"].casefold()
        if normalized_key in seen_commands:
            continue
        seen_commands.add(normalized_key)
        accepted_suggestions.append(result)
        audit_rows.append({
            "command": result["command"],
            "normalized_command": result["normalized_command"],
            "risk_label": result["risk_label"],
            "validation_result": result["validation_result"],
            "rejection_reason": result["rejection_reason"],
            "target": result["target"],
            "target_allowed": result["target_allowed"],
        })
        if result["validation_result"] == "rejected":
            app_metrics.record_ai_suggestion_rejection(result["rejection_reason"])
        if len(accepted_suggestions) >= 3:
            break

    _log_validation_result(
        accepted_suggestions,
        trusted_target_count=len(trusted_targets),
        known_port_count=len(known_ports),
    )
    return {"suggestions": accepted_suggestions}, audit_rows


def _log_validation_result(
    suggestions: list[dict[str, Any]],
    *,
    trusted_target_count: int,
    known_port_count: int,
) -> None:
    accepted_count = sum(1 for item in suggestions if item.get("validation_result") == "accepted")
    rejected_reasons = Counter(
        str(item.get("rejection_reason") or "unknown")
        for item in suggestions
        if item.get("validation_result") == "rejected"
    )
    rejected_count = sum(rejected_reasons.values())
    reason_counts = dict(sorted(rejected_reasons.items()))
    extra = {
        "suggestion_count": len(suggestions),
        "accepted_count": accepted_count,
        "rejected_count": rejected_count,
        "rejection_reasons": reason_counts,
        "trusted_target_count": trusted_target_count,
        "known_port_count": known_port_count,
    }
    log.debug("AI_SUGGESTION_VALIDATION_COMPLETED", extra=extra)
    if suggestions and accepted_count == 0 and rejected_count:
        log.warning("AI_SUGGESTIONS_REJECTED", extra=extra)


def _validate_one(
    item: dict[str, Any],
    *,
    trusted_targets: set[str],
    source_targets: set[str],
    source_fingerprint: tuple[Any, ...] | None,
    known_ports: set[int],
    session_id: str,
    cfg: dict,
) -> dict[str, Any]:
    command = str(item.get("command") or "").strip()
    normalized = unicodedata.normalize("NFKC", command)
    unicode_changed = normalized != command
    risk_label = str(item.get("risk_label") or "unknown").strip().lower()
    target = str(item.get("target") or _safe_extract_target(normalized) or "").strip()
    normalized, target, unresolved_placeholder = _replace_source_target_placeholder(normalized, target, source_targets)
    normalized, target = _replace_target_redaction_placeholders(normalized, target, source_targets)
    root = output_command_root(normalized) or ""
    normalized, wordlist_rejection = _normalize_command_wordlists(normalized, root)
    command_target = _safe_extract_target(normalized)
    rejection_reason = ""
    target_allowed = False
    unresolved_target_alias = len(source_targets) != 1 and (
        _TARGET_REDACTION_RE.search(normalized) is not None
        or _TARGET_REDACTION_RE.search(target) is not None
    )

    if unicode_changed:
        rejection_reason = "unicode_obfuscation"
    elif unresolved_placeholder:
        rejection_reason = "target_absent"
    elif wordlist_rejection:
        rejection_reason = wordlist_rejection
    elif _contains_redaction_marker(normalized, target, cfg):
        rejection_reason = "redaction_sentinel"
    else:
        validation = validate_command(normalized, session_id=session_id, cfg=cfg)
        if not validation.allowed:
            rejection_reason = _policy_rejection_reason(validation.reason)
        elif _missing_required_secret(normalized, session_id):
            rejection_reason = "missing_secret"
        elif _known_invalid_flag(normalized, root):
            rejection_reason = "invalid_flag"
        else:
            if root in NETWORK_TARGET_ROOTS:
                if not command_target:
                    rejection_reason = "command_target_absent"
                else:
                    target = command_target
                    target_allowed = _target_allowed(target, trusted_targets)
                    if not target_allowed:
                        rejection_reason = "target_absent"
                    else:
                        unknown_ports = _suggested_ports(normalized, root) - known_ports
                        if known_ports and unknown_ports:
                            rejection_reason = "port_absent"
                        elif _is_duplicate_source_command(normalized, source_fingerprint, source_targets):
                            rejection_reason = "duplicate_source"
            elif not target and root not in NO_TARGET_ALLOWLIST:
                rejection_reason = "unknown_root"
            elif target:
                target_allowed = _target_allowed(target, trusted_targets)
                if not target_allowed:
                    rejection_reason = "target_absent"
                else:
                    unknown_ports = _suggested_ports(normalized, root) - known_ports
                    if known_ports and unknown_ports:
                        rejection_reason = "port_absent"
                    elif _is_duplicate_source_command(normalized, source_fingerprint, source_targets):
                        rejection_reason = "duplicate_source"

    if unresolved_placeholder or unresolved_target_alias:
        display_command = _display_unresolved_source_target(normalized)
        display_target = _display_unresolved_source_target(target)
    else:
        display_command = normalized
        display_target = target

    return {
        "command": display_command[:2000],
        "normalized_command": display_command[:2000],
        "reason": str(item.get("reason") or "").strip()[:240],
        "risk_label": risk_label if risk_label in {"low", "medium", "high", "unknown"} else "unknown",
        "target": display_target[:500] if display_target else None,
        "target_allowed": bool(target_allowed),
        "validation_result": "rejected" if rejection_reason else "accepted",
        "rejection_reason": rejection_reason,
    }


def _trusted_targets(context: dict[str, Any], project_targets: list[dict[str, Any]]) -> set[str]:
    targets: set[str] = set()

    def add(value: object) -> None:
        for candidate in _target_candidates(value):
            targets.add(candidate)

    run_value = context.get("run")
    run: dict[str, Any] = run_value if isinstance(run_value, dict) else {}
    add(run.get("target"))
    add(_safe_extract_target(str(run.get("command") or "")))
    entities = context.get("entities")
    if isinstance(entities, dict):
        for values in entities.values():
            if isinstance(values, list):
                for value in values:
                    add(value)
    for target in project_targets:
        if isinstance(target, dict):
            add(target.get("value"))
    return targets


def known_open_port_labels(context: dict[str, Any]) -> list[str]:
    """Return stable labels such as ``80/tcp`` from trusted source-run context."""
    labels: set[str] = set()
    for text in _context_signal_text(context):
        for match in _OPEN_PORT_RE.finditer(text):
            labels.add(f"{int(match.group('port'))}/{match.group('proto').lower()}")
        for match in _DISCOVERED_OPEN_PORT_RE.finditer(text):
            labels.add(f"{int(match.group('port'))}/{match.group('proto').lower()}")
    return sorted(labels, key=lambda label: (label.rsplit("/", 1)[1], int(label.split("/", 1)[0])))


def known_open_ports(context: dict[str, Any]) -> set[int]:
    ports: set[int] = set()
    for label in known_open_port_labels(context):
        port = int(label.split("/", 1)[0])
        if 0 < port <= 65535:
            ports.add(port)
    return ports


def _context_signal_text(context: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for section in ("findings", "transcript_tail", "warnings_errors"):
        values = context.get(section)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            for key in ("line", "text", "title"):
                value = str(item.get(key) or "").strip()
                if value:
                    rows.append(value)
    return rows


def _source_targets(context: dict[str, Any], project_targets: list[dict[str, Any]]) -> set[str]:
    targets: set[str] = set()
    for target in project_targets:
        if not isinstance(target, dict):
            continue
        if str(target.get("type") or "") != "source_run_target":
            continue
        for candidate in _target_candidates(target.get("value")):
            targets.add(candidate)
    run_value = context.get("run")
    run: dict[str, Any] = run_value if isinstance(run_value, dict) else {}
    context_targets: set[str] = set()
    for value in (run.get("target"), _safe_extract_target(str(run.get("command") or ""))):
        for candidate in _target_candidates(value):
            context_targets.add(candidate)
    if len(targets) == 1:
        return targets
    if len(context_targets) == 1:
        return context_targets
    if targets:
        return targets
    targets.update(context_targets)
    return targets


def source_targets_from_context(context: dict[str, Any], project_targets: list[dict[str, Any]] | None = None) -> set[str]:
    """Return the single-source target candidates used for AI placeholder repair."""
    return _source_targets(context, project_targets or [])


def replace_source_target_aliases(text: object, source_targets: set[str]) -> str:
    """Replace SOURCE_TARGET or target redaction markers when exactly one source target is known."""
    value = str(text or "")
    if len(source_targets) != 1:
        return value
    source_target = next(iter(source_targets))
    return _TARGET_REDACTION_RE.sub(source_target, _SOURCE_TARGET_RE.sub(source_target, value))


def replace_target_aliases_for_display(
    text: object,
    source_targets: set[str],
    *,
    unresolved: str = _UNRESOLVED_TARGET_DISPLAY,
) -> str:
    """Replace target aliases for user-visible output without pretending ambiguous targets are known."""
    value = replace_source_target_aliases(text, source_targets)
    if len(source_targets) == 1:
        return value
    return _TARGET_REDACTION_RE.sub(unresolved, _SOURCE_TARGET_RE.sub(unresolved, value))


def _replace_source_target_placeholder(command: str, target: str, source_targets: set[str]) -> tuple[str, str, bool]:
    if "SOURCE_TARGET" not in command and "SOURCE_TARGET" not in target:
        return command, target, False
    if len(source_targets) != 1:
        return command, target, True
    replaced_command = replace_source_target_aliases(command, source_targets)
    replaced_target = replace_source_target_aliases(target, source_targets)
    unresolved = "SOURCE_TARGET" in replaced_command or "SOURCE_TARGET" in replaced_target
    return replaced_command, replaced_target, unresolved


def _display_unresolved_source_target(value: str) -> str:
    return replace_target_aliases_for_display(value, set())


def _replace_target_redaction_placeholders(command: str, target: str, source_targets: set[str]) -> tuple[str, str]:
    if not _TARGET_REDACTION_RE.search(command) and not _TARGET_REDACTION_RE.search(target):
        return command, target
    if len(source_targets) != 1:
        return command, target
    return replace_source_target_aliases(command, source_targets), replace_source_target_aliases(target, source_targets)


def _target_candidates(value: object) -> set[str]:
    text = str(value or "").strip()
    if not text:
        return set()
    candidates: set[str] = set()
    for part in text.replace("\n", ",").split(","):
        try:
            cleaned = _normalize_target(part)
        except ValueError:
            cleaned = ""
        if cleaned and not _is_target_redaction_marker(cleaned):
            candidates.add(cleaned)
    return candidates


def _safe_extract_target(command: str) -> str:
    try:
        return str(extract_target(command) or "").strip()
    except ValueError:
        return ""


def _normalize_target(value: object) -> str:
    text = str(value or "").strip().strip("[]").rstrip(".")
    if not text:
        return ""
    parsed = urlparse(text if "://" in text else f"//{text}")
    host = parsed.hostname or text.split("/", 1)[0].split(":", 1)[0]
    host = host.strip().strip("[]").rstrip(".").lower()
    if not host:
        return ""
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return host


def _target_allowed(target: str, trusted_targets: set[str]) -> bool:
    candidates = _target_candidates(target)
    if not candidates:
        return False
    return any(candidate in trusted_targets for candidate in candidates)


def _known_invalid_flag(command: str, root: str) -> bool:
    invalid_flags = _KNOWN_INVALID_FLAGS.get(root)
    if not invalid_flags:
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    return any(token in invalid_flags for token in tokens[1:])


def _normalize_command_wordlists(command: str, root: str) -> tuple[str, str]:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return command, "policy_rejected"
    wordlist_flags = _wordlist_flags_for_command(tokens, root)
    if not wordlist_flags:
        return command, ""
    changed = False
    for index, token in enumerate(tokens):
        flag = token
        value = ""
        inline = False
        if "=" in token:
            flag, value = token.split("=", 1)
            inline = True
        elif token in wordlist_flags and index + 1 < len(tokens):
            value = tokens[index + 1]
        if flag not in wordlist_flags or not value:
            continue
        normalized, rejection = _normalize_wordlist_path(value, categories=wordlist_flags.get(flag) or set())
        if rejection:
            return command, rejection
        if normalized == value:
            continue
        changed = True
        if inline:
            tokens[index] = f"{flag}={normalized}"
        else:
            tokens[index + 1] = normalized
    return (shlex.join(tokens) if changed else command), ""


def _normalize_wordlist_path(value: str, *, categories: set[str] | None = None) -> tuple[str, str]:
    path = str(value or "").strip()
    if not path:
        return path, ""
    if not path.startswith("/"):
        return path, ""
    catalog = _wordlist_catalog_index()
    root = str(catalog.get("root") or "").rstrip("/")
    if root and path == root:
        return path, ""
    if root and path.startswith(f"{root}/"):
        return path, ""
    canonical = _catalog_wordlist_match(path, catalog, categories or set())
    if canonical:
        return canonical, ""
    if _looks_like_packaged_wordlist(path):
        return path, "wordlist_absent"
    return path, ""


def _wordlist_flags_for_command(tokens: list[str], root: str) -> dict[str, set[str]]:
    spec = _autocomplete_spec_for_tokens(tokens, root)
    flags = _wordlist_flags_from_autocomplete_spec(spec)
    if flags:
        return flags
    fallback = _FALLBACK_WORDLIST_FLAGS_BY_ROOT.get(root, {})
    return {flag: set(categories) for flag, categories in fallback.items()}


def _autocomplete_spec_for_tokens(tokens: list[str], root: str) -> dict[str, Any]:
    context = _autocomplete_context()
    spec = context.get(root)
    if not isinstance(spec, dict):
        return {}
    subcommands = spec.get("subcommands")
    if isinstance(subcommands, dict) and len(tokens) > 1:
        subcommand = str(tokens[1] or "").strip().lower()
        sub_spec = subcommands.get(subcommand)
        if isinstance(sub_spec, dict):
            return sub_spec
    return spec


def _wordlist_flags_from_autocomplete_spec(spec: dict[str, Any]) -> dict[str, set[str]]:
    flags: dict[str, set[str]] = {}
    arg_hints = spec.get("arg_hints")
    if not isinstance(arg_hints, dict):
        return flags
    for trigger, hints in arg_hints.items():
        token = str(trigger or "").strip()
        if not token or token == "__positional__" or not isinstance(hints, list):
            continue
        categories: set[str] = set()
        has_wordlist_hint = False
        for hint in hints:
            if not isinstance(hint, dict):
                continue
            if str(hint.get("value_type") or "").strip().lower() != "wordlist":
                continue
            has_wordlist_hint = True
            categories.update(_wordlist_categories_from_hint(hint.get("wordlist_category")))
        if has_wordlist_hint:
            flags[token] = categories
    return flags


def _wordlist_categories_from_hint(value: object) -> set[str]:
    if isinstance(value, str):
        return {value.strip().lower()} if value.strip() else set()
    if isinstance(value, (list, tuple, set)):
        return {str(item or "").strip().lower() for item in value if str(item or "").strip()}
    return set()


@lru_cache(maxsize=1)
def _autocomplete_context() -> dict[str, Any]:
    try:
        context = load_autocomplete_context_from_commands_registry({"workspace_enabled": True})
    except Exception:
        return {}
    return context if isinstance(context, dict) else {}


@lru_cache(maxsize=1)
def _wordlist_catalog_index() -> dict[str, Any]:
    catalog = load_wordlist_catalog()
    root = str(catalog.get("root") or "").rstrip("/")
    entries: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add_entry(category: object, relpath: object, path: object = "") -> None:
        category_text = str(category or "").strip().lower()
        relpath_text = str(relpath or "").strip().lstrip("/")
        if not category_text or not relpath_text:
            return
        path_text = str(path or "").strip()
        if not path_text:
            path_text = f"{root}/{relpath_text}" if root else relpath_text
        key = (category_text, relpath_text.casefold())
        if key in seen:
            return
        seen.add(key)
        entries.append({
            "category": category_text,
            "name": Path(relpath_text).name.casefold(),
            "relpath": relpath_text.casefold(),
            "path": path_text,
        })

    for category in catalog.get("categories") or []:
        if not isinstance(category, dict):
            continue
        for relpath in category.get("include") or []:
            text = str(relpath or "").strip()
            if text and not any(char in text for char in "*?["):
                add_entry(category.get("key"), text)
    for item in catalog.get("items") or []:
        if isinstance(item, dict):
            add_entry(item.get("category"), item.get("relpath"), item.get("path"))
    return {"root": root, "entries": entries}


def _catalog_wordlist_match(path: str, catalog: dict[str, Any], categories: set[str]) -> str:
    requested_name = Path(path).name.casefold()
    if not requested_name:
        return ""
    candidate_entries = [
        item for item in catalog.get("entries") or []
        if isinstance(item, dict)
        and item.get("name") == requested_name
        and (not categories or str(item.get("category") or "") in categories)
    ]
    unique_paths = sorted({str(item.get("path") or "") for item in candidate_entries if item.get("path")})
    return unique_paths[0] if len(unique_paths) == 1 else ""


def _looks_like_packaged_wordlist(path: str) -> bool:
    return (
        path.startswith("/usr/share/wordlists/")
        or path.startswith("/usr/share/dirb/")
        or path.startswith("/usr/share/seclists/")
    )


def _source_command_fingerprint(context: dict[str, Any], source_targets: set[str]) -> tuple[Any, ...] | None:
    run_value = context.get("run")
    run: dict[str, Any] = run_value if isinstance(run_value, dict) else {}
    command = str(run.get("command") or "").strip()
    if not command:
        return None
    command = replace_source_target_aliases(command, source_targets)
    root = output_command_root(command) or ""
    command, rejection = _normalize_command_wordlists(command, root)
    if rejection:
        return None
    return _command_fingerprint(command, source_targets)


def _is_duplicate_source_command(
    command: str,
    source_fingerprint: tuple[Any, ...] | None,
    source_targets: set[str],
) -> bool:
    if source_fingerprint is None:
        return False
    if source_fingerprint[0] not in _DUPLICATE_SOURCE_ROOTS:
        return False
    return _command_fingerprint(command, source_targets) == source_fingerprint


def _command_fingerprint(command: str, source_targets: set[str]) -> tuple[Any, ...] | None:
    try:
        tokens = shlex.split(replace_source_target_aliases(command, source_targets))
    except ValueError:
        tokens = command.split()
    if not tokens:
        return None
    root = output_command_root(command) or tokens[0].lower()
    subcommand = tokens[1].lower() if root == "gobuster" and len(tokens) > 1 else ""
    target = _safe_extract_target(command)
    target_key = ""
    if target:
        candidates = sorted(_target_candidates(target))
        target_key = candidates[0] if candidates else ""
    return (
        root,
        subcommand,
        target_key,
        tuple(sorted(_suggested_ports(command, root))),
        tuple(_command_option_values(tokens, {"--script", "-script", "-x"})),
        tuple(_command_wordlist_values(tokens, root)),
    )


def _command_option_values(tokens: list[str], option_names: set[str]) -> list[str]:
    values: list[str] = []
    for index, token in enumerate(tokens):
        flag = token
        value = ""
        if "=" in token:
            flag, value = token.split("=", 1)
        elif token in option_names and index + 1 < len(tokens):
            value = tokens[index + 1]
        if flag in option_names and value:
            values.append(f"{flag}={_normalize_fingerprint_option_value(flag, value)}")
    return sorted(values)


def _normalize_fingerprint_option_value(flag: str, value: str) -> str:
    normalized = str(value or "").strip().casefold()
    if flag in {"--script", "-script", "-x"}:
        parts = [part.strip() for part in re.split(r"[,;]", normalized) if part.strip()]
        if parts:
            return ",".join(sorted(parts))
    return normalized


def _command_wordlist_values(tokens: list[str], root: str) -> list[str]:
    wordlist_flags = _wordlist_flags_for_command(tokens, root)
    values: list[str] = []
    for index, token in enumerate(tokens):
        flag = token
        value = ""
        if "=" in token:
            flag, value = token.split("=", 1)
        elif token in wordlist_flags and index + 1 < len(tokens):
            value = tokens[index + 1]
        if flag not in wordlist_flags or not value:
            continue
        normalized, rejection = _normalize_wordlist_path(value, categories=wordlist_flags.get(flag) or set())
        if not rejection:
            values.append(normalized.casefold())
    return sorted(values)


def _suggested_ports(command: str, root: str) -> set[int]:
    ports: set[int] = set()
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    for index, token in enumerate(tokens):
        if root == "nmap":
            if token in _NMAP_PORT_FLAGS and index + 1 < len(tokens):
                ports.update(_parse_port_spec(tokens[index + 1]))
            elif token.startswith("--ports="):
                ports.update(_parse_port_spec(token.split("=", 1)[1]))
            elif token.startswith("-p") and token not in {"-p", "-Pn"}:
                ports.update(_parse_port_spec(token[2:]))
        ports.update(_ports_from_target_token(token))
    return ports


def _parse_port_spec(value: str) -> set[int]:
    ports: set[int] = set()
    for part in re.split(r"[,/]", str(value or "")):
        item = part.strip()
        if not item:
            continue
        item = re.sub(r"^(?:[TUSPN]:)+", "", item, flags=re.I)
        if "-" in item:
            start_text, end_text = item.split("-", 1)
            if start_text.isdigit() and end_text.isdigit():
                start = max(1, int(start_text))
                end = min(65535, int(end_text))
                if start <= end:
                    ports.update(range(start, end + 1))
            continue
        if item.isdigit():
            port = int(item)
            if 0 < port <= 65535:
                ports.add(port)
    return ports


def _ports_from_target_token(token: str) -> set[int]:
    text = str(token or "").strip().strip("[]")
    if not text or text.startswith("-"):
        return set()
    try:
        parsed = urlparse(text if "://" in text else f"//{text}")
    except ValueError:
        return set()
    try:
        port = parsed.port
    except ValueError:
        return set()
    if port and 0 < port <= 65535:
        return {port}
    return set()


def _is_target_redaction_marker(value: str) -> bool:
    return bool(_TARGET_REDACTION_RE.fullmatch(str(value or "").strip()))


def _contains_redaction_marker(command: str, target: str, cfg: dict) -> bool:
    if _TARGET_REDACTION_RE.search(command) or _TARGET_REDACTION_RE.search(target):
        return True
    markers = {REDACTED_ENTITY_SENTINEL, "[secret-name-redacted]"}
    for rule in get_share_redaction_rules(cfg):
        replacement = rule.get("replacement")
        if isinstance(replacement, str) and replacement:
            markers.add(replacement)
    return any(marker and (marker in command or marker in target) for marker in markers)


def _missing_required_secret(command: str, session_id: str) -> bool:
    for declaration in required_secrets_for_command(command):
        if bool(declaration.get("optional", False)):
            continue
        env_name = str(declaration.get("env") or "").strip().upper()
        fallback_envs = declaration.get("fallback_envs")
        lookup_envs = [env_name]
        if isinstance(fallback_envs, list):
            lookup_envs.extend(str(item or "").strip().upper() for item in fallback_envs if str(item or "").strip())
        try:
            if not any(get_secret_value_for_env(session_id, env_name) is not None for env_name in lookup_envs if env_name):
                return True
        except (MasterKeyError, SecretDecryptError, ValueError) as exc:
            log.warning(
                "AI_SUGGESTION_SECRET_LOOKUP_FAILED",
                exc_info=True,
                extra={
                    "session": get_log_session_id(session_id),
                    "env": env_name,
                    "error_type": type(exc).__name__,
                },
            )
            return True
    return False


def _policy_rejection_reason(reason: str) -> str:
    lowered = str(reason or "").lower()
    if "shell operators" in lowered:
        return "shell_chain"
    if "secret" in lowered or "vault" in lowered:
        return "missing_secret"
    if "local host" in lowered or "127.0.0.1" in lowered:
        return "private_network"
    if "not allowed" in lowered:
        return "unknown_root"
    if "not permitted" in lowered:
        return "denied_flag"
    return "policy_rejected"
