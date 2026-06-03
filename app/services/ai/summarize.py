"""Summary assist orchestration and deterministic repairs."""

from __future__ import annotations

import json
import logging
import re

from services.ai.client import AIClientError, AIProviderResult, OpenAICompatibleClient
from services.ai.prompts import (
    RUN_CONTEXT_CLOSE,
    RUN_CONTEXT_OPEN,
    SYSTEM_PROMPT,
    UNTRUSTED_OUTPUT_CLOSE,
    UNTRUSTED_OUTPUT_OPEN,
    developer_prompt,
)
from services.ai.schemas import validate_summary_payload
from services.ai.suggestions import replace_target_aliases_for_display, source_targets_from_context

log = logging.getLogger("shell")

_SUMMARY_MAX_KEY_FINDINGS = 20
_SUMMARY_MAX_WARNINGS = 8
_SUMMARY_MAX_OUTPUT_TOKENS = 120
_PORT_FINDING_RE = re.compile(
    r"^\s*(?P<port>\d{1,5}/(?:tcp|udp))\s+(?:open(?:\S*)?|is\s+open)\b.*$",
    re.IGNORECASE,
)
_DISCOVERED_PORT_RE = re.compile(
    r"\bDiscovered\s+open\s+port\s+(?P<port>\d{1,5}/(?:tcp|udp))\b",
    re.IGNORECASE,
)
_NO_OPEN_PORTS_RE = re.compile(
    r"\b(?:no|zero|0)\s+(?:open\s+)?(?:tcp\s+|udp\s+)?ports?\b|\bno\s+open\s+ports?\s+found\b",
    re.IGNORECASE,
)
_OPEN_PORT_COUNT_RE = re.compile(
    r"\b(?P<count>\d{1,4})\s+open\s+(?:tcp\s+|udp\s+)?ports?\b(?:\s*\([^)]*\))?",
    re.IGNORECASE,
)
_NO_FINDINGS_RE = re.compile(r"\bno\s+(?:actionable\s+)?findings?\b", re.IGNORECASE)


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
    """Ask the provider for summary prose and merge deterministic signal lines."""
    source_targets = source_targets_from_context(context, assist.get("project_target_snapshot") or [])
    result = _provider_result(client, messages(context, source_targets=source_targets), context, active_cfg, assist_id, run_id)
    payload = merge_context_findings(result.payload, context, source_targets=source_targets)
    return payload, result, [], 0, 0


def messages(context: dict, *, source_targets: set[str] | None = None) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": developer_prompt("summary")},
        {"role": "user", "content": _message_content(context, source_targets=source_targets)},
    ]


def _provider_result(
    client: OpenAICompatibleClient,
    provider_messages: list[dict[str, str]],
    context: dict,
    active_cfg: dict,
    assist_id: str,
    run_id: str,
) -> AIProviderResult:
    try:
        return client.chat_completion(
            provider_messages,
            validate=validate_summary_payload,
            max_tokens=min(
                _SUMMARY_MAX_OUTPUT_TOKENS,
                int(active_cfg.get("ai_max_output_tokens") or _SUMMARY_MAX_OUTPUT_TOKENS),
            ),
            metric_variant="summary",
            retry_on_schema_error=False,
        )
    except AIClientError as exc:
        if not _is_truncation(exc):
            raise
        result = _fallback_result(context)
        log.info("AI_ASSIST_SUMMARY_FALLBACK", extra={
            "assist_id": assist_id,
            "run_id": run_id,
            "variant": "summary",
            "reason": "provider_truncated",
        })
        return result


def _message_content(context: dict, *, source_targets: set[str] | None = None) -> str:
    run_value = context.get("run")
    run: dict = run_value if isinstance(run_value, dict) else {}
    findings = context.get("findings") if isinstance(context.get("findings"), list) else []
    triage_findings = (
        context.get("triage_findings")
        if isinstance(context.get("triage_findings"), list)
        else []
    )
    exploit_backed = (
        context.get("exploit_backed_findings")
        if isinstance(context.get("exploit_backed_findings"), list)
        else []
    )
    warnings_errors = context.get("warnings_errors") if isinstance(context.get("warnings_errors"), list) else []
    transcript_tail = context.get("transcript_tail") if isinstance(context.get("transcript_tail"), list) else []
    lines = [
        f"{RUN_CONTEXT_OPEN}",
        f"command: {run.get('command') or ''}",
        f"target: {run.get('target') or ''}",
        *(["source_target_alias: SOURCE_TARGET"] if source_targets and len(source_targets) == 1 else []),
        f"run_kind: {run.get('run_kind') or ''}",
        f"exit_code: {run.get('exit_code')}",
        f"runtime_seconds: {run.get('runtime_seconds')}",
        f"output_truncated: {bool(run.get('output_truncated'))}",
        f"{RUN_CONTEXT_CLOSE}",
        f"{UNTRUSTED_OUTPUT_OPEN}",
        "findings:",
    ]
    if findings:
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            finding_text = " ".join(
                str(part)
                for part in (
                    finding.get("severity") or "",
                    finding.get("kind") or "",
                    finding.get("title") or "",
                    finding.get("line") or "",
                )
                if part
            )
            lines.append(f"- {finding.get('line_number')}: {finding_text}")
    else:
        lines.append("- none")
    if triage_findings:
        lines.append("triage_findings:")
        for finding in triage_findings:
            if not isinstance(finding, dict):
                continue
            lines.append(f"- {_triage_finding_line(finding)}")
    if exploit_backed:
        lines.append("exploit_backed_findings:")
        for finding in exploit_backed:
            if not isinstance(finding, dict):
                continue
            lines.append(f"- {_exploit_backed_line(finding)}")
    if warnings_errors:
        lines.append("warnings_errors:")
        for item in warnings_errors:
            if not isinstance(item, dict):
                continue
            lines.append(f"- {item.get('line_index')}: {item.get('text') or ''}")
    lines.append("transcript_tail:")
    if transcript_tail:
        for item in transcript_tail:
            if not isinstance(item, dict):
                continue
            lines.append(f"{item.get('line_index')}: {item.get('text') or ''}")
    else:
        lines.append("- none")
    lines.append(f"{UNTRUSTED_OUTPUT_CLOSE}")
    return "\n".join(lines)


def _triage_finding_line(finding: dict) -> str:
    details = []
    for key, label in (
        ("remediation", "remediation"),
        ("verification_steps", "verify"),
    ):
        value = str(finding.get(key) or "").strip()
        if value:
            details.append(f"{label}={value}")
    parts = [
        str(finding.get("severity") or "info"),
        str(finding.get("title") or "").strip(),
        f"verification={finding.get('verification_status') or 'not_started'}",
        *details,
    ]
    return " ".join(part for part in parts if part)


def _exploit_backed_line(finding: dict) -> str:
    subject = " ".join(
        str(part)
        for part in (
            finding.get("target") or "",
            finding.get("service") or "",
        )
        if part
    )
    title = str(finding.get("cve") or finding.get("title") or "").strip()
    raw_references = finding.get("references")
    references = raw_references if isinstance(raw_references, list) else []
    reference_text = ", ".join(str(item) for item in references[:3] if item)
    parts = [
        str(finding.get("severity") or "info"),
        subject,
        title,
        f"exploit_count={int(finding.get('exploit_count') or 0)}",
    ]
    if reference_text:
        parts.append(f"refs={reference_text}")
    return " ".join(part for part in parts if part)


def _is_truncation(exc: AIClientError) -> bool:
    return exc.code == "ai_malformed" and "truncated" in str(exc).lower()


def _fallback_result(context: dict) -> AIProviderResult:
    context_findings = _context_key_findings(context)
    port_count = len({key for key in (_finding_key(item) for item in context_findings) if key.startswith("port:")})
    if port_count:
        plural = "port" if port_count == 1 else "ports"
        summary = f"The scan found {port_count} open {plural}."
        next_steps_hint = "Review exposed services and follow up on any unexpected open ports."
    else:
        run_value = context.get("run")
        run: dict = run_value if isinstance(run_value, dict) else {}
        command_parts = str(run.get("command") or "").strip().split()
        command_root = command_parts[0] if command_parts else "Command"
        summary = f"{command_root} completed and produced structured output."
        next_steps_hint = "Review the captured signals and raw output for details."
    payload = validate_summary_payload({
        "summary": summary,
        "key_findings": [],
        "warnings": [],
        "next_steps_hint": next_steps_hint,
    })
    raw_content = json.dumps({"fallback": "summary_truncated", **payload}, separators=(",", ":"), sort_keys=True)
    return AIProviderResult(
        payload=payload,
        raw_content=raw_content,
        finish_reason="fallback",
        duration_ms=0,
        output_chars=len(raw_content),
    )


def merge_context_findings(payload: dict, context: dict, *, source_targets: set[str] | None = None) -> dict:
    context_findings = _context_key_findings(context)
    context_warnings = _context_warnings(context)
    exploit_backed_count = _exploit_backed_count(context)
    aliases = source_targets or set()
    merged = []
    seen_keys: set[str] = set()
    seen_text: set[str] = set()

    def add(text: str) -> None:
        cleaned = " ".join(_display_summary_target_aliases(text, aliases).split())
        if not cleaned:
            return
        text_key = cleaned.casefold()
        finding_key = _finding_key(cleaned)
        if text_key in seen_text or (finding_key and finding_key in seen_keys):
            return
        seen_text.add(text_key)
        if finding_key:
            seen_keys.add(finding_key)
        merged.append(cleaned[:500])

    for item in context_findings:
        add(item)

    port_count = len({key for key in seen_keys if key.startswith("port:")})
    summary = _display_summary_target_aliases(
        _repair_text(
            payload.get("summary"),
            port_count=port_count,
            finding_count=len(merged),
            exploit_backed_count=exploit_backed_count,
            field="summary",
        ),
        aliases,
    )
    next_steps_hint = _display_summary_target_aliases(
        _repair_text(
            payload.get("next_steps_hint"),
            port_count=port_count,
            finding_count=len(merged),
            exploit_backed_count=exploit_backed_count,
            field="next_steps_hint",
        ),
        aliases,
    )
    return {
        **payload,
        "summary": summary,
        "key_findings": merged[:_SUMMARY_MAX_KEY_FINDINGS],
        "warnings": [
            " ".join(_display_summary_target_aliases(item, aliases).split())
            for item in context_warnings[:_SUMMARY_MAX_WARNINGS]
        ],
        "next_steps_hint": next_steps_hint,
    }


def _display_summary_target_aliases(text: object, source_targets: set[str]) -> str:
    return replace_target_aliases_for_display(text, source_targets, unresolved="the scanned targets")


def _context_key_findings(context: dict) -> list[str]:
    findings: list[str] = []
    seen: set[str] = set()

    def maybe_add(text: object) -> None:
        cleaned = " ".join(str(text or "").split())
        if not cleaned:
            return
        key = _finding_key(cleaned) or cleaned.casefold()
        if key in seen:
            return
        seen.add(key)
        findings.append(cleaned)

    for finding in context.get("findings") or []:
        if not isinstance(finding, dict):
            continue
        maybe_add(finding.get("line") or finding.get("title"))
    for finding in context.get("exploit_backed_findings") or []:
        if not isinstance(finding, dict):
            continue
        maybe_add(_exploit_backed_line(finding))
    for item in context.get("transcript_tail") or []:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if _finding_key(str(text or "")):
            maybe_add(text)
    return findings


def _exploit_backed_count(context: dict) -> int:
    rows = context.get("exploit_backed_findings")
    if not isinstance(rows, list):
        return 0
    return sum(1 for row in rows if isinstance(row, dict))


def _context_warnings(context: dict) -> list[str]:
    warnings: list[str] = []
    seen: set[str] = set()
    for item in context.get("warnings_errors") or []:
        if not isinstance(item, dict):
            continue
        cleaned = " ".join(str(item.get("text") or "").split())
        key = cleaned.casefold()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        warnings.append(cleaned[:500])
    return warnings


def _finding_key(text: str) -> str:
    port_match = _PORT_FINDING_RE.match(text)
    if port_match:
        return f"port:{port_match.group('port').lower()}"
    discovered_match = _DISCOVERED_PORT_RE.search(text)
    if discovered_match:
        return f"port:{discovered_match.group('port').lower()}"
    return ""


def _repair_text(text: object, *, port_count: int, finding_count: int, exploit_backed_count: int, field: str) -> str:
    cleaned = " ".join(str(text or "").split())
    has_no_findings_claim = bool(_NO_FINDINGS_RE.search(cleaned))
    if has_no_findings_claim and finding_count > 0:
        if field == "next_steps_hint":
            if exploit_backed_count > 0:
                return "Review exploit-backed findings and prioritize affected services."
            return "Review the reported findings and prioritize follow-up."
        if exploit_backed_count > 0:
            return "The scan found exploit-backed findings."
        return "The scan found actionable findings."
    cleaned = _NO_FINDINGS_RE.sub("no actionable issues", cleaned)
    if port_count <= 0:
        return cleaned
    if _NO_OPEN_PORTS_RE.search(cleaned):
        if field == "next_steps_hint":
            return "Review exposed services and follow up on any unexpected open ports."
        plural = "port" if port_count == 1 else "ports"
        return f"The scan found {port_count} open {plural}."

    def replace_count(match: re.Match[str]) -> str:
        if int(match.group("count")) == port_count:
            return match.group(0)
        plural = "port" if port_count == 1 else "ports"
        return f"{port_count} open {plural} detected"

    repaired = _OPEN_PORT_COUNT_RE.sub(replace_count, cleaned, count=1)
    if repaired != cleaned:
        return repaired
    return cleaned
