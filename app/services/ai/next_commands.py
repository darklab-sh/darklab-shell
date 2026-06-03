"""Next-command assist orchestration."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from services.ai.client import AIClientError, AIProviderResult, OpenAICompatibleClient
from services.ai.prompts import (
    NEXT_COMMAND_ALLOWED_TOOLS,
    RUN_CONTEXT_CLOSE,
    RUN_CONTEXT_OPEN,
    SYSTEM_PROMPT,
    UNTRUSTED_OUTPUT_CLOSE,
    UNTRUSTED_OUTPUT_OPEN,
    developer_prompt,
)
from services.ai.schemas import validate_next_commands_payload
from services.ai.suggestions import known_open_port_labels, validate_suggestions

_ENTITY_TYPES = ("ip", "domain", "url")
_OPEN_PORT_FACT_LIMIT = 10
_SIGNAL_LINE_LIMIT = 5
_ENTITY_SAMPLE_LIMIT = 4
_WEB_CONTENT_WORDLISTS = (
    "/usr/share/wordlists/seclists/Discovery/Web-Content/common.txt",
    "/usr/share/wordlists/seclists/Discovery/Web-Content/big.txt",
    "/usr/share/wordlists/seclists/Discovery/Web-Content/raft-small-directories.txt",
)
_WEB_WORDLIST_ROOTS = frozenset({"ffuf", "gobuster"})
_WEB_SERVICE_PORTS = frozenset({80, 443, 8000, 8008, 8080, 8081, 8088, 8443})
_WEB_SERVICE_RE = re.compile(r"\b(?:http|https|ssl/http|http-proxy|webdav)\b", re.I)
_OPEN_PORT_LINE_RE = re.compile(r"\b(?P<port>\d{1,5})/(?P<proto>tcp|udp)\s+(?P<detail>open\S*\s+.*)$", re.I)
log = logging.getLogger("shell")


def run(
    client: OpenAICompatibleClient,
    *,
    context: dict,
    active_cfg: dict,
    assist: dict,
    session_id: str,
    assist_id: str,
    run_id: str,
) -> tuple[dict, AIProviderResult, list[dict], int, int]:
    """Ask the provider for next commands and validate every suggestion."""
    try:
        result = client.chat_completion(
            messages(context),
            validate=validate_next_commands_payload,
            max_tokens=int(active_cfg.get("ai_next_commands_max_output_tokens") or 180),
            metric_variant="next_commands",
            retry_on_schema_error=True,
        )
    except AIClientError as exc:
        if not _is_truncation(exc):
            raise
        result = _fallback_result(assist_id, run_id)
    payload, validation_rows = validate_suggestions(
        result.payload,
        context=context,
        session_id=session_id,
        project_target_snapshot=assist.get("project_target_snapshot") or [],
        cfg=active_cfg,
    )
    suggestion_count = len(payload.get("suggestions") or [])
    rejected_count = sum(1 for item in payload.get("suggestions") or [] if item.get("validation_result") != "accepted")
    return payload, result, validation_rows, suggestion_count, rejected_count


def _is_truncation(exc: AIClientError) -> bool:
    return exc.code == "ai_malformed" and "truncated" in str(exc).lower()


def _fallback_result(assist_id: str, run_id: str) -> AIProviderResult:
    payload = validate_next_commands_payload({"suggestions": []})
    raw_content = json.dumps({"fallback": "next_commands_truncated", **payload}, separators=(",", ":"), sort_keys=True)
    log.info("AI_ASSIST_NEXT_COMMANDS_FALLBACK", extra={
        "assist_id": assist_id,
        "run_id": run_id,
        "variant": "next_commands",
        "reason": "provider_truncated",
    })
    return AIProviderResult(
        payload=payload,
        raw_content=raw_content,
        finish_reason="fallback",
        duration_ms=0,
        output_chars=len(raw_content),
    )


def messages(context: dict) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": developer_prompt("next_commands")},
        {"role": "user", "content": _message_content(context)},
    ]


def _message_content(context: dict) -> str:
    run_value = context.get("run")
    run: dict = run_value if isinstance(run_value, dict) else {}
    output_summary_value = context.get("output_summary")
    output_summary: dict[str, Any] = output_summary_value if isinstance(output_summary_value, dict) else {}
    signal_lines = _signal_lines(context)
    wordlist_menu = _web_wordlist_menu(context, run)
    lines = [
        f"{RUN_CONTEXT_OPEN}",
        f"source_command_root: {_command_root(run.get('command'))}",
        f"source_command: {_clean_line(run.get('command'))[:180] or 'unknown'}",
        "source_target_alias: SOURCE_TARGET",
        f"allowed_command_roots: {', '.join(NEXT_COMMAND_ALLOWED_TOOLS)}",
        f"open_ports: {_open_port_facts(context)}",
        f"entities: {_entity_facts(context)}",
        f"exit_code: {run.get('exit_code')}",
        f"signals: {_summary_facts(output_summary)}",
        "task: return one service-specific follow-up, not a repeat scan",
        f"{RUN_CONTEXT_CLOSE}",
        f"{UNTRUSTED_OUTPUT_OPEN}",
        "signal_lines:",
    ]
    if wordlist_menu:
        lines.insert(5, wordlist_menu)
    if signal_lines:
        lines.extend(f"- {line}" for line in signal_lines)
    else:
        lines.append("- none")
    lines.append(f"{UNTRUSTED_OUTPUT_CLOSE}")
    return "\n".join(lines)


def _command_root(command: object) -> str:
    return str(command or "").strip().split(maxsplit=1)[0].lower() or "unknown"


def _web_wordlist_menu(context: dict, run: dict) -> str:
    if _should_include_web_wordlists(context, run):
        return f"approved_web_wordlists: {', '.join(_WEB_CONTENT_WORDLISTS)}"
    return ""


def _should_include_web_wordlists(context: dict, run: dict) -> bool:
    if _command_root(run.get("command")) in _WEB_WORDLIST_ROOTS:
        return True
    for label in known_open_port_labels(context):
        port_text = label.split("/", 1)[0]
        if port_text.isdigit() and int(port_text) in _WEB_SERVICE_PORTS:
            return True
    if any(_WEB_SERVICE_RE.search(line) for line in _context_lines(context)):
        return True
    entities_value = context.get("entities")
    entities: dict[str, Any] = entities_value if isinstance(entities_value, dict) else {}
    urls = entities.get("url")
    return isinstance(urls, list) and any(str(url).lower().startswith(("http://", "https://")) for url in urls)


def _open_port_facts(context: dict) -> str:
    details = _open_port_details(context)
    labels = known_open_port_labels(context)
    facts = [details.get(label, label) for label in labels[:_OPEN_PORT_FACT_LIMIT]]
    if len(labels) > _OPEN_PORT_FACT_LIMIT:
        facts.append(f"{len(labels) - _OPEN_PORT_FACT_LIMIT} more")
    return "; ".join(facts) if facts else "none"


def _open_port_details(context: dict) -> dict[str, str]:
    details: dict[str, str] = {}
    for line in _context_lines(context):
        match = _OPEN_PORT_LINE_RE.search(line)
        if not match:
            continue
        label = f"{int(match.group('port'))}/{match.group('proto').lower()}"
        details.setdefault(label, f"{label} {match.group('detail').strip()}"[:120])
    return details


def _entity_facts(context: dict) -> str:
    entities_value = context.get("entities")
    entities: dict[str, Any] = entities_value if isinstance(entities_value, dict) else {}
    facts: list[str] = []
    for entity_type in _ENTITY_TYPES:
        values = entities.get(entity_type)
        if not isinstance(values, list) or not values:
            continue
        samples = [_clean_line(value)[:80] for value in values[:_ENTITY_SAMPLE_LIMIT] if _clean_line(value)]
        sample_text = ", ".join(samples)
        suffix = f" ({sample_text})" if sample_text else ""
        facts.append(f"{entity_type}s={len(values)}{suffix}")
    return "; ".join(facts) if facts else "none"


def _summary_facts(output_summary: dict[str, Any]) -> str:
    facts: list[str] = []
    for family in ("signal", "role", "kind"):
        values = output_summary.get(family)
        if not isinstance(values, dict):
            continue
        pairs = [
            f"{key}:{int(value)}"
            for key, value in sorted(values.items())
            if isinstance(key, str) and isinstance(value, int) and value
        ]
        if pairs:
            facts.append(f"{family}={','.join(pairs[:6])}")
    return "; ".join(facts) if facts else "none"


def _signal_lines(context: dict) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for line in [*_open_port_details(context).values(), *_context_lines(context)]:
        cleaned = _clean_line(line)
        key = cleaned.casefold()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        lines.append(cleaned[:160])
        if len(lines) >= _SIGNAL_LINE_LIMIT:
            break
    return lines


def _context_lines(context: dict) -> list[str]:
    rows: list[str] = []
    for section in ("exploit_backed_findings", "findings", "warnings_errors"):
        values = context.get(section)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            if section == "exploit_backed_findings":
                value = _exploit_backed_context_line(item)
                if value:
                    rows.append(value)
                    continue
            for key in ("line", "text", "title"):
                value = _clean_line(item.get(key))
                if value:
                    rows.append(value)
                    break
    return rows


def _exploit_backed_context_line(item: dict) -> str:
    raw_references = item.get("references")
    references = raw_references if isinstance(raw_references, list) else []
    reference_text = " ".join(str(reference) for reference in references[:2] if reference)
    return _clean_line(
        " ".join(
            str(part)
            for part in (
                item.get("severity") or "info",
                item.get("target") or "",
                item.get("service") or "",
                item.get("cve") or item.get("title") or "",
                f"exploit_count={int(item.get('exploit_count') or 0)}",
                reference_text,
            )
            if part
        )
    )


def _clean_line(value: object) -> str:
    return " ".join(str(value or "").split())
