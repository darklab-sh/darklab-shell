"""TLS certificate diff classifier for openssl s_client output."""

from __future__ import annotations

import re
from typing import Any

from services.diff.classifiers import register_classifier
from services.diff.classifiers.common import command_root, normalized_lines
from services.diff.models import DIFF_KIND_NONE, DIFF_KIND_SIGNAL, DiffResult

_FIELD_PATTERNS = {
    "subject": re.compile(r"^subject\s*=\s*(?P<value>.+)$", re.I),
    "issuer": re.compile(r"^issuer\s*=\s*(?P<value>.+)$", re.I),
    "not_before": re.compile(r"^notBefore\s*=\s*(?P<value>.+)$", re.I),
    "not_after": re.compile(r"^notAfter\s*=\s*(?P<value>.+)$", re.I),
    "sha256_fingerprint": re.compile(r"^SHA256 Fingerprint\s*=\s*(?P<value>.+)$", re.I),
    "verify_return_code": re.compile(r"^Verify return code:\s*(?P<value>.+)$", re.I),
}
_SAN_HEADER_RE = re.compile(r"^(?:X509v3\s+)?Subject Alternative Name\s*:?(?P<value>.*)$", re.I)
_SAN_VALUE_RE = re.compile(r"^(?:DNS|IP Address|IP|email|URI):", re.I)


def _normalized_sans(values: list[str]) -> str:
    entries = []
    for value in values:
        entries.extend(part.strip() for part in value.split(",") if part.strip())
    return ", ".join(sorted(set(entries), key=str.lower))


def applies_to(command_text: str, _run: dict[str, Any], _conn=None) -> bool:
    return command_root(command_text) == "openssl" and "s_client" in str(command_text or "")


def _fields(run: dict[str, Any]) -> tuple[dict[str, str], bool]:
    lines, output_info = normalized_lines(run)
    fields: dict[str, str] = {}
    san_values = []
    reading_sans = False
    for line in lines:
        san_header = _SAN_HEADER_RE.match(line)
        if san_header:
            reading_sans = True
            inline_value = san_header.group("value").strip()
            if inline_value:
                san_values.append(inline_value)
            continue
        if reading_sans and _SAN_VALUE_RE.match(line):
            san_values.append(line)
            continue
        reading_sans = False
        for field, pattern in _FIELD_PATTERNS.items():
            match = pattern.match(line)
            if match:
                fields[field] = match.group("value").strip()
    if san_values:
        fields["subject_alt_names"] = _normalized_sans(san_values)
    return fields, bool(output_info.get("partial"))


@register_classifier("tls", applies_to=applies_to)
def diff(
    baseline_run: dict[str, Any],
    current_run: dict[str, Any],
    _options: dict[str, bool] | None = None,
    _conn=None,
) -> DiffResult:
    left, left_partial = _fields(baseline_run)
    right, right_partial = _fields(current_run)
    changed = []
    for field in sorted(set(left) | set(right)):
        before = left.get(field, "")
        after = right.get(field, "")
        if before != after:
            changed.append({"field": field, "before": before, "after": after})
    summary = {
        "classifier": "tls",
        "changed_tls_field_count": len(changed),
        "changed_tls_fields": changed[:1000],
    }
    return DiffResult(
        summary=summary,
        kind=DIFF_KIND_SIGNAL if changed else DIFF_KIND_NONE,
        truncated=left_partial or right_partial or len(changed) > 1000,
    )
