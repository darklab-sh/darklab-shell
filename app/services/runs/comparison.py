"""Shared run comparison helpers for history and project responses."""

import re
import shlex
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlparse

from core.output_signals import (
    classify_line,
    command_root as output_command_root,
    extract_target,
    strip_ansi_codes,
)
from services.intel.canonical import CanonicalizationError, canonical_url
from services.diff.models import DIFF_KIND_NONE
from services.runs.output_model import LineEvent
from services.runs.output_model import is_noise_event, noise_kind_for_event
from services.runs.output_store import load_run_output_events_for_run

MAX_COMPARE_ITEMS_PER_SIDE = 5000
COMPARE_MAX_LINES = 20_000
COMPARE_MAX_BYTES = 3 * 1024 * 1024
COMPARE_MAX_CHANGED_LINES = 2_000
COMPARE_MAX_HUNKS = 3_000
COMPARE_INLINE_EQUAL_CONTEXT = 3
COMPARE_LINE_DISPLAY_TRUNCATE = 4_000
COMPARE_LAZY_EQUAL_PAGE_LIMIT = 5_000
COMPARE_LAZY_EQUAL_BYTE_LIMIT = 512_000
COMPARE_REPLACE_PAIR_MIN_RATIO = 0.5
COMPARE_REPLACE_PAIR_QUICK_RATIO = COMPARE_REPLACE_PAIR_MIN_RATIO
COMPARE_REPLACE_PAIR_CANDIDATES = 32
COMPARE_MINIMAP_BUCKETS = 256
COMPARE_DERIVED_CHANGE_LIMIT = 1000
URL_COMPARE_ROOTS = {"httpx", "ffuf", "gobuster", "katana"}
_HTTPX_COMPARE_RE = re.compile(r"^(?P<url>https?://\S+)\s+(?P<brackets>(?:\[[^\]]*\]\s*)+)$", re.I)
_FFUF_COMPARE_RE = re.compile(
    r"^(?P<path>.+?)\s+\[Status:\s*(?P<status>\d{3}),\s*Size:\s*\d+,\s*"
    r"Words:\s*\d+,\s*Lines:\s*\d+,\s*Duration:\s*[^\]]+\]$",
    re.I,
)
_GOBUSTER_COMPARE_RE = re.compile(
    r"^(?P<path>\S(?:.*\S)?)\s+\(Status:\s*(?P<status>\d{3})\)\s+"
    r"\[Size:\s*\d+\](?:\s+\[-->\s+(?P<redirect>\S+)\])?$",
    re.I,
)
_CLEAN_HTTP_URL_RE = re.compile(r"^https?://\S+$", re.I)
_SHELL_TEMPLATE_URL_NOISE_RE = re.compile(r"(?:'\+|\+'\$|/\$1\b)")


def compare_item_limit(limit=None):
    if limit is None:
        limit = MAX_COMPARE_ITEMS_PER_SIDE
    try:
        return max(0, int(limit))
    except (TypeError, ValueError):
        return MAX_COMPARE_ITEMS_PER_SIDE


def finding_compare_key(row):
    for value in (row["raw_line"], row["title"]):
        normalized = re.sub(r"\s+", " ", strip_ansi_codes(str(value or ""))).strip()
        if normalized:
            return normalized
    return row["fingerprint"] or ""


def run_finding_compare_items(
    conn,
    session_id,
    run_id,
    *,
    include_line_number=False,
    include_created=False,
):
    limit = compare_item_limit()
    total = conn.execute(
        "SELECT COUNT(*) AS count "
        "FROM findings_occurrences fo JOIN findings f ON f.id = fo.finding_id "
        "WHERE f.session_id = ? AND fo.run_id = ?",
        (session_id, run_id),
    ).fetchone()["count"]
    rows = conn.execute(
        "SELECT f.id, f.raw_line, f.title, f.severity, f.fingerprint, f.status AS review_state, "
        "fo.line_number, f.created "
        "FROM findings_occurrences fo JOIN findings f ON f.id = fo.finding_id "
        "WHERE f.session_id = ? AND fo.run_id = ? ORDER BY fo.line_number ASC, f.id ASC LIMIT ?",
        (session_id, run_id, limit),
    ).fetchall()
    items = []
    for row in rows:
        item = {
            "key": finding_compare_key(row),
            "id": row["id"],
            "title": row["title"] or "",
            "raw_line": row["raw_line"] or "",
            "severity": row["severity"] or "",
            "review_state": row["review_state"] or "",
        }
        if include_line_number:
            item["line_number"] = row["line_number"]
        if include_created:
            item["created"] = row["created"]
        items.append(item)
    total = int(total or 0)
    return items, total, total > len(items)


def run_artifact_compare_items(
    conn,
    session_id,
    run_id,
    *,
    include_display_name=False,
    include_created=False,
):
    limit = compare_item_limit()
    total = conn.execute(
        "SELECT COUNT(*) AS count FROM run_file_artifacts WHERE session_id = ? AND run_id = ?",
        (session_id, run_id),
    ).fetchone()["count"]
    rows = conn.execute(
        "SELECT id, workspace_path, display_name, kind, byte_size, detected_by, content_sha256, created "
        "FROM run_file_artifacts WHERE session_id = ? AND run_id = ? ORDER BY created ASC, id ASC LIMIT ?",
        (session_id, run_id, limit),
    ).fetchall()
    items = []
    for row in rows:
        item = {
            "key": row["content_sha256"] or row["workspace_path"] or row["id"],
            "id": row["id"],
            "workspace_path": row["workspace_path"] or "",
            "kind": row["kind"] or "",
            "byte_size": row["byte_size"],
            "detected_by": row["detected_by"] or "",
            "content_sha256": row["content_sha256"] or "",
        }
        if include_display_name:
            item["display_name"] = row["display_name"] or ""
        if include_created:
            item["created"] = row["created"]
        items.append(item)
    total = int(total or 0)
    return items, total, total > len(items)


def compare_items(left_items, right_items):
    left_counts = Counter(item["key"] for item in left_items if item.get("key"))
    right_counts = Counter(item["key"] for item in right_items if item.get("key"))
    added_remaining = right_counts - left_counts
    removed_remaining = left_counts - right_counts

    def _collect(source_items, remaining):
        rows = []
        seen = Counter()
        for item in source_items:
            key = item.get("key")
            if not key or remaining[key] <= seen[key]:
                continue
            seen[key] += 1
            rows.append(item)
        return rows

    return {
        "added": _collect(right_items, added_remaining),
        "removed": _collect(left_items, removed_remaining),
        "unchanged_count": sum((left_counts & right_counts).values()),
    }


def compare_line_index_by_output_line(entries):
    indexes = {}
    for compare_index, entry in enumerate(entries):
        line_index = entry.get("line_index")
        if isinstance(line_index, int) and not isinstance(line_index, bool) and line_index not in indexes:
            indexes[line_index] = compare_index
    return indexes


def _enrich_compare_line_indexes(items, index_by_output_line):
    enriched = []
    for item in items:
        enriched_item = dict(item)
        line_number = enriched_item.get("line_number")
        if isinstance(line_number, int) and not isinstance(line_number, bool):
            compare_line_index = index_by_output_line.get(line_number)
            if compare_line_index is not None:
                enriched_item["compare_line_index"] = compare_line_index
        enriched.append(enriched_item)
    return enriched


def add_compare_line_indexes(finding_diff, left_entries, right_entries):
    left_index_by_line = compare_line_index_by_output_line(left_entries)
    right_index_by_line = compare_line_index_by_output_line(right_entries)
    return {
        **finding_diff,
        "added": _enrich_compare_line_indexes(finding_diff.get("added", []), right_index_by_line),
        "removed": _enrich_compare_line_indexes(finding_diff.get("removed", []), left_index_by_line),
    }


def _enrich_derived_line_pointer(item, index_by_output_line, side):
    enriched_item = dict(item)
    line_index = enriched_item.get("line_index")
    if isinstance(line_index, int) and not isinstance(line_index, bool):
        compare_line_index = index_by_output_line.get(line_index)
        if compare_line_index is not None:
            enriched_item["compare_line_index"] = compare_line_index
            enriched_item["compare_side"] = side
    return enriched_item


def _port_group_display(left_run, right_run):
    left_target = compare_run_target(left_run)
    right_target = compare_run_target(right_run)
    left_root = compare_run_root(left_run)
    right_root = compare_run_root(right_run)
    display_target = right_target or left_target or right_root or left_root or "nmap"
    return {
        "command_root": right_root or left_root,
        "target": right_target or left_target,
        "left_target": left_target,
        "right_target": right_target,
        "display_target": display_target,
        "target_ambiguous": bool(left_target and right_target and left_target != right_target),
    }


def _compare_nmap_port_changes(left_run, right_run, left_entries, right_entries):
    from services.diff.classifiers import ports as port_diff_classifier  # noqa: PLC0415

    command_text = str(right_run.get("command") or left_run.get("command") or "")
    if not port_diff_classifier.applies_to(command_text, right_run):
        return None

    diff = port_diff_classifier.diff(left_run, right_run, None, None)
    summary = diff.summary
    if diff.kind == DIFF_KIND_NONE:
        return None

    left_index_by_line = compare_line_index_by_output_line(left_entries)
    right_index_by_line = compare_line_index_by_output_line(right_entries)
    added = [
        _enrich_derived_line_pointer(item, right_index_by_line, "right")
        for item in summary.get("added_ports", [])[:COMPARE_DERIVED_CHANGE_LIMIT]
    ]
    removed = [
        _enrich_derived_line_pointer(item, left_index_by_line, "left")
        for item in summary.get("removed_ports", [])[:COMPARE_DERIVED_CHANGE_LIMIT]
    ]
    changed = []
    for item in summary.get("changed_ports", [])[:COMPARE_DERIVED_CHANGE_LIMIT]:
        changed.append({
            "key": item.get("key"),
            "before": _enrich_derived_line_pointer(
                item.get("before", {}),
                left_index_by_line,
                "left",
            ),
            "after": _enrich_derived_line_pointer(
                item.get("after", {}),
                right_index_by_line,
                "right",
            ),
        })

    return {
        "id": "nmap_ports",
        "kind": "ports",
        "classifier": "ports",
        "title": "Open ports and services",
        **_port_group_display(left_run, right_run),
        "added": added,
        "removed": removed,
        "changed": changed,
        "added_count": int(summary.get("added_port_count") or 0),
        "removed_count": int(summary.get("removed_port_count") or 0),
        "changed_count": int(summary.get("changed_port_count") or 0),
        "suppressed_removed_count": int(summary.get("suppressed_removed_port_count") or 0),
        "truncated": bool(diff.truncated),
    }


def _command_flag_value(command, names):
    try:
        tokens = shlex.split(str(command or ""))
    except ValueError:
        tokens = str(command or "").split()
    for index, token in enumerate(tokens):
        if token in names and index + 1 < len(tokens):
            return tokens[index + 1]
        for name in names:
            prefix = f"{name}="
            if token.startswith(prefix):
                return token[len(prefix):]
    return ""


def _command_url_template(command):
    return _command_flag_value(command, {"-u", "--url", "-target", "--target"})


def _join_base_url(base, path):
    raw_path = str(path or "").strip()
    if not raw_path:
        return ""
    if _CLEAN_HTTP_URL_RE.match(raw_path):
        return raw_path
    parsed = urlparse(str(base or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    if "FUZZ" in str(base):
        return str(base).replace("FUZZ", raw_path.lstrip("/"), 1)
    if raw_path.startswith("/"):
        return f"{parsed.scheme}://{parsed.netloc}{raw_path}"
    return f"{str(base).rstrip('/')}/{raw_path.lstrip('/')}"


def _canonical_compare_url(value):
    try:
        return canonical_url(value)
    except CanonicalizationError:
        return ""


def _parse_httpx_url_record(text, command):
    match = _HTTPX_COMPARE_RE.match(text)
    if not match:
        return None
    url = match.group("url")
    canonical = _canonical_compare_url(url)
    if not canonical:
        return None
    bracket_values = re.findall(r"\[([^\]]*)\]", match.group("brackets") or "")
    record = {"key": canonical, "url": url, "canonical_url": canonical}
    extra_values = []
    for value in bracket_values:
        stripped = value.strip()
        if not stripped:
            continue
        if re.fullmatch(r"\d{3}", stripped):
            record["status_code"] = int(stripped)
        elif _CLEAN_HTTP_URL_RE.match(stripped):
            redirect_canonical = _canonical_compare_url(stripped)
            if redirect_canonical:
                record["redirect_url"] = stripped
                record["redirect_canonical_url"] = redirect_canonical
        else:
            extra_values.append(stripped)
    if extra_values and "-title" in str(command or ""):
        record["title"] = extra_values[0]
    if extra_values:
        record["labels"] = extra_values
    return record


def _parse_ffuf_url_record(text, command):
    match = _FFUF_COMPARE_RE.match(text)
    if not match:
        return None
    url = _join_base_url(_command_url_template(command), match.group("path"))
    canonical = _canonical_compare_url(url)
    if not canonical:
        return None
    return {
        "key": canonical,
        "url": url,
        "canonical_url": canonical,
        "status_code": int(match.group("status")),
    }


def _parse_gobuster_url_record(text, command):
    match = _GOBUSTER_COMPARE_RE.match(text)
    if not match:
        return None
    url = _join_base_url(_command_url_template(command), match.group("path"))
    canonical = _canonical_compare_url(url)
    if not canonical:
        return None
    record = {
        "key": canonical,
        "url": url,
        "canonical_url": canonical,
        "status_code": int(match.group("status")),
    }
    redirect = str(match.group("redirect") or "").strip()
    redirect_canonical = _canonical_compare_url(redirect) if redirect else ""
    if redirect_canonical:
        record["redirect_url"] = redirect
        record["redirect_canonical_url"] = redirect_canonical
    return record


def _parse_katana_url_record(text):
    if not _CLEAN_HTTP_URL_RE.match(text) or _SHELL_TEMPLATE_URL_NOISE_RE.search(text):
        return None
    canonical = _canonical_compare_url(text)
    if not canonical:
        return None
    return {"key": canonical, "url": text, "canonical_url": canonical}


def _parse_url_record(root, text, command):
    stripped = strip_ansi_codes(str(text or "")).strip()
    if root == "httpx":
        return _parse_httpx_url_record(stripped, command)
    if root == "ffuf":
        return _parse_ffuf_url_record(stripped, command)
    if root == "gobuster":
        return _parse_gobuster_url_record(stripped, command)
    if root == "katana":
        return _parse_katana_url_record(stripped)
    return None


def _url_entity_record(entry):
    for entity in entry.get("entities") or []:
        if not isinstance(entity, dict) or str(entity.get("type") or "") != "url":
            continue
        canonical = str(entity.get("canonical_value") or entity.get("value") or "").strip()
        if not canonical:
            continue
        return {
            "key": canonical.casefold(),
            "url": str(entity.get("value") or canonical),
            "canonical_url": canonical,
        }
    return None


def _url_records_for_compare(run, entries):
    root = compare_run_root(run)
    if root not in URL_COMPARE_ROOTS:
        return {}
    command = str(run.get("command") or "")
    records = {}
    for entry in entries:
        parsed = _parse_url_record(root, entry.get("text"), command)
        entity_record = _url_entity_record(entry)
        record: dict[str, Any] | None = entity_record or parsed
        if parsed and entity_record:
            record = {**entity_record, **parsed, "key": parsed["key"].casefold()}
        elif parsed:
            record = {**parsed, "key": parsed["key"].casefold()}
        if not record:
            continue
        line_index = entry.get("line_index")
        if isinstance(line_index, int) and not isinstance(line_index, bool):
            record["line_index"] = line_index
        record["line"] = str(entry.get("text") or "")
        records[record["key"]] = record
    return records


def _url_signature(record):
    return (
        str(record.get("status_code") or ""),
        str(record.get("title") or "").strip().casefold(),
        str(record.get("redirect_canonical_url") or "").strip().casefold(),
    )


def _compare_url_changes(left_run, right_run, left_entries, right_entries):
    left_root = compare_run_root(left_run)
    right_root = compare_run_root(right_run)
    if left_root not in URL_COMPARE_ROOTS and right_root not in URL_COMPARE_ROOTS:
        return None

    left = _url_records_for_compare(left_run, left_entries)
    right = _url_records_for_compare(right_run, right_entries)
    added_keys = sorted(set(right) - set(left))
    removed_keys = sorted(set(left) - set(right))
    changed_keys = sorted(
        key for key in set(left) & set(right)
        if _url_signature(left[key]) != _url_signature(right[key])
    )
    if not added_keys and not removed_keys and not changed_keys:
        return None

    left_index_by_line = compare_line_index_by_output_line(left_entries)
    right_index_by_line = compare_line_index_by_output_line(right_entries)
    added = [
        _enrich_derived_line_pointer(right[key], right_index_by_line, "right")
        for key in added_keys[:COMPARE_DERIVED_CHANGE_LIMIT]
    ]
    removed = [
        _enrich_derived_line_pointer(left[key], left_index_by_line, "left")
        for key in removed_keys[:COMPARE_DERIVED_CHANGE_LIMIT]
    ]
    changed = [
        {
            "key": key,
            "before": _enrich_derived_line_pointer(left[key], left_index_by_line, "left"),
            "after": _enrich_derived_line_pointer(right[key], right_index_by_line, "right"),
        }
        for key in changed_keys[:COMPARE_DERIVED_CHANGE_LIMIT]
    ]
    total_emitted = len(added) + len(removed) + len(changed)
    total_changes = len(added_keys) + len(removed_keys) + len(changed_keys)
    return {
        "id": "web_urls",
        "kind": "urls",
        "classifier": "urls",
        "title": "URLs and HTTP status",
        "command_root": right_root or left_root,
        "target": compare_run_target(right_run) or compare_run_target(left_run),
        "display_target": compare_run_target(right_run)
        or compare_run_target(left_run)
        or right_root
        or left_root
        or "web",
        "added": added,
        "removed": removed,
        "changed": changed,
        "added_count": len(added_keys),
        "removed_count": len(removed_keys),
        "changed_count": len(changed_keys),
        "truncated": total_changes > total_emitted,
    }


def compare_derived_changes(left_run, right_run, left_entries, right_entries):
    groups = []
    port_group = _compare_nmap_port_changes(left_run, right_run, left_entries, right_entries)
    if port_group is not None:
        groups.append(port_group)
    url_group = _compare_url_changes(left_run, right_run, left_entries, right_entries)
    if url_group is not None:
        groups.append(url_group)
    total_change_count = sum(
        int(group.get("added_count") or 0)
        + int(group.get("removed_count") or 0)
        + int(group.get("changed_count") or 0)
        for group in groups
    )
    return {
        "groups": groups,
        "group_count": len(groups),
        "changed_count": total_change_count,
        "truncated": any(bool(group.get("truncated")) for group in groups),
    }


def normalize_compare_command(command):
    return re.sub(r"\s+", " ", str(command or "").strip())


def parse_iso_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def run_duration_seconds(run):
    started = parse_iso_datetime(run.get("started"))
    finished = parse_iso_datetime(run.get("finished"))
    if not started or not finished:
        return None
    return max(0.0, (finished - started).total_seconds())


def compare_run_root(run):
    return output_command_root(str(run.get("command") or ""))


def compare_run_target(run):
    target = extract_target(str(run.get("command") or ""))
    return target or ""


def compare_run_summary(run):
    duration = run_duration_seconds(run)
    command = str(run.get("command") or "")
    root = compare_run_root(run)
    target = compare_run_target(run)
    return {
        "id": run.get("id"),
        "command": command,
        "command_root": root,
        "target": target,
        "started": run.get("started"),
        "finished": run.get("finished"),
        "exit_code": run.get("exit_code"),
        "duration_seconds": duration,
        "output_line_count": int(run.get("output_line_count") or 0),
        "preview_truncated": bool(run.get("preview_truncated")),
        "full_output_available": bool(run.get("full_output_available")),
        "full_output_truncated": bool(run.get("full_output_truncated")),
    }


def candidate_confidence(source, candidate):
    source_command = normalize_compare_command(source.get("command")).lower()
    candidate_command = normalize_compare_command(candidate.get("command")).lower()
    if source_command and source_command == candidate_command:
        return 3, "exact_command", "Exact command"
    source_root = compare_run_root(source)
    candidate_root = compare_run_root(candidate)
    source_target = compare_run_target(source)
    candidate_target = compare_run_target(candidate)
    if source_root and source_root == candidate_root and source_target and source_target == candidate_target:
        return 2, "same_target", "Same target"
    if source_root and source_root == candidate_root:
        return 1, "same_command", "Same command only"
    return 0, "", ""


def run_candidate_payload(row, source):
    run = dict(row)
    score, confidence, label = candidate_confidence(source, run)
    payload = compare_run_summary(run)
    payload.update({
        "confidence": confidence,
        "confidence_label": label,
        "score": score,
    })
    return payload


def compare_full_output_events(run):
    result = load_run_output_events_for_run(run, log_event="COMPARE_FULL_OUTPUT_LOAD_FAILED")
    return result.events, result.source, result.partial


def compare_line_exclusion(event: LineEvent, text):
    stripped = str(text or "").strip()
    if not stripped:
        return "blank", ""
    if is_noise_event(event):
        noise_kind = noise_kind_for_event(event)
        return "noise", noise_kind.value if noise_kind is not None else ""
    if event.role.value in {"prompt-echo", "pty-marker"}:
        return "chrome", event.role.value
    if re.match(r"^\[(?:process exited with code|history\s+—\s+exit)\b", stripped, re.I):
        return "chrome", "exit"
    return None


def is_compare_chrome_line(event: LineEvent, text):
    return compare_line_exclusion(event, text) is not None


def line_entry_text(entry):
    if isinstance(entry, dict):
        return str(entry.get("text", ""))
    return str(entry or "")


def compare_entries_for_diff(run):
    events, source, partial = compare_full_output_events(run)
    compared = []
    byte_count = 0
    truncated_by_limit = False
    noise_counts: Counter[str] = Counter()
    chrome_lines_omitted = 0
    for event in events:
        text = event.text.rstrip("\n")
        exclusion = compare_line_exclusion(event, text)
        if exclusion is not None:
            reason, detail = exclusion
            if reason == "noise":
                noise_counts[detail or "unknown"] += 1
            else:
                chrome_lines_omitted += 1
            continue
        encoded_len = len(text.encode("utf-8", errors="replace"))
        if len(compared) >= COMPARE_MAX_LINES or byte_count + encoded_len > COMPARE_MAX_BYTES:
            truncated_by_limit = True
            break
        item = {
            "text": text,
            "line_index": event.line_index,
            "signals": [signal.value for signal in event.signals],
            "kind": event.kind.value,
            "role": event.role.value,
            "entities": [entity.to_wire() for entity in event.entities],
        }
        compared.append(item)
        byte_count += encoded_len
    return compared, {
        "source": source,
        "partial": partial or truncated_by_limit,
        "truncated_by_limit": truncated_by_limit,
        "compared_lines": len(compared),
        "max_lines": COMPARE_MAX_LINES,
        "max_bytes": COMPARE_MAX_BYTES,
        "noise_lines_omitted": sum(noise_counts.values()),
        "noise_kind_counts": dict(sorted(noise_counts.items())),
        "chrome_lines_omitted": chrome_lines_omitted,
    }


def finding_count_for_entries(run, entries):
    root = compare_run_root(run)
    command = str(run.get("command") or "")
    count = 0
    previous_text = ""
    for entry in entries:
        text = str(entry.get("text") or "")
        signals = entry.get("signals")
        if isinstance(signals, list):
            scopes = [str(signal) for signal in signals]
        else:
            scopes = classify_line(text, command=command, root=root, previous_text=previous_text)
        if "findings" in scopes:
            count += 1
        previous_text = text.strip()
    return count


def compare_line_payload(entry):
    payload = {
        "text": str(entry.get("text") or ""),
        "line_index": entry.get("line_index"),
    }
    for key in ("kind", "role", "signals", "entities"):
        if entry.get(key):
            payload[key] = entry[key]
    return payload


def compare_line_payloads(entries, start, end):
    return [compare_line_payload(entry) for entry in entries[start:end]]


def _all_compare_entries_have_line_indexes(left_entries, right_entries):
    entries = [*left_entries, *right_entries]
    return bool(entries) and all(
        isinstance(entry.get("line_index"), int) and not isinstance(entry.get("line_index"), bool)
        for entry in entries
    )


def compare_line_sequence_key(entry, *, use_line_index):
    text = str(entry.get("text") or "")
    if not use_line_index:
        return text
    return (
        entry.get("line_index"),
        text,
        str(entry.get("kind") or ""),
        str(entry.get("role") or ""),
    )


def compare_line_structural_changed(left_line, right_line):
    return any(
        str(left_line.get(key) or "") != str(right_line.get(key) or "")
        for key in ("kind", "role")
    )


def compare_line_structural_payload(line):
    return {
        key: str(line.get(key) or "")
        for key in ("kind", "role")
        if line.get(key)
    }


_LINE_KIND_SEVERITY = {
    "info": 0,
    "notice": 1,
    "warn": 2,
    "error": 3,
}


def compare_line_severity_kind(lines):
    best = ""
    best_score = -1
    for line in lines:
        kind = str(line.get("kind") or "")
        score = _LINE_KIND_SEVERITY.get(kind, -1)
        if score > best_score:
            best = kind
            best_score = score
    return best


def compare_hunk_severity_kind(hunk):
    lines = []
    if hunk["op"] == "insert":
        lines.extend(hunk.get("right", {}).get("lines", []))
    elif hunk["op"] == "delete":
        lines.extend(hunk.get("left", {}).get("lines", []))
    elif hunk["op"] == "replace":
        left_lines = hunk.get("left", {}).get("lines", [])
        right_lines = hunk.get("right", {}).get("lines", [])
        lines.extend(left_lines)
        lines.extend(right_lines)
    severity = compare_line_severity_kind(lines)
    if severity:
        hunk["severity_kind"] = severity
    return hunk


def compare_entity_sets(left_entries, right_entries):
    def _entities_by_key(entries):
        entities = {}
        for entry in entries:
            for entity in entry.get("entities") or []:
                if not isinstance(entity, dict):
                    continue
                entity_type = str(entity.get("type") or "").strip()
                canonical = str(entity.get("canonical_value") or entity.get("value") or "").strip()
                if not entity_type or not canonical:
                    continue
                key = f"{entity_type}:{canonical}".casefold()
                entities.setdefault(key, {
                    "type": entity_type,
                    "value": str(entity.get("value") or canonical),
                    "canonical_value": canonical,
                    "confidence": str(entity.get("confidence") or "medium"),
                })
        return entities

    left_entities = _entities_by_key(left_entries)
    right_entities = _entities_by_key(right_entries)
    added_keys = sorted(set(right_entities) - set(left_entities))
    removed_keys = sorted(set(left_entities) - set(right_entities))
    unchanged_keys = set(left_entities).intersection(right_entities)
    return {
        "added": [right_entities[key] for key in added_keys],
        "removed": [left_entities[key] for key in removed_keys],
        "unchanged_count": len(unchanged_keys),
    }


def compare_line_events(left: Sequence[LineEvent], right: Sequence[LineEvent]):
    def _entry(event: LineEvent):
        return {
            "text": event.text,
            "line_index": event.line_index,
            "signals": [signal.value for signal in event.signals],
            "kind": event.kind.value,
            "role": event.role.value,
            "entities": [entity.to_wire() for entity in event.entities],
        }

    return hunk_line_diff([_entry(event) for event in left], [_entry(event) for event in right])


def changed_line_segments(left_text, right_text):
    matcher = SequenceMatcher(None, left_text, right_text, autojunk=False)
    left_segments = []
    right_segments = []
    for tag, left_start, left_end, right_start, right_end in matcher.get_opcodes():
        left_chunk = left_text[left_start:left_end]
        right_chunk = right_text[right_start:right_end]
        changed = tag != "equal"
        if left_chunk:
            left_segments.append({"text": left_chunk, "changed": changed})
        if right_chunk:
            right_segments.append({"text": right_chunk, "changed": changed})
    return left_segments, right_segments


def compare_equal_hunk(left_entries, right_entries, left_start, left_end, right_start, right_end, inline_context):
    hunk = {
        "op": "equal",
        "left": {"start": left_start, "end": left_end},
        "right": {"start": right_start, "end": right_end},
    }
    line_count = left_end - left_start
    if line_count < 2 * inline_context:
        hunk["left"]["lines"] = compare_line_payloads(left_entries, left_start, left_end)
        hunk["right"]["lines"] = compare_line_payloads(right_entries, right_start, right_end)
        return hunk
    left_leading_end = min(left_end, left_start + inline_context)
    right_leading_end = min(right_end, right_start + inline_context)
    left_trailing_start = max(left_leading_end, left_end - inline_context)
    right_trailing_start = max(right_leading_end, right_end - inline_context)
    hunk["context"] = {
        "leading": {
            "left": compare_line_payloads(left_entries, left_start, left_leading_end),
            "right": compare_line_payloads(right_entries, right_start, right_leading_end),
        },
        "trailing": {
            "left": compare_line_payloads(left_entries, left_trailing_start, left_end),
            "right": compare_line_payloads(right_entries, right_trailing_start, right_end),
        },
        "omitted": max(0, line_count - (2 * inline_context)),
    }
    return hunk


def replace_pair_candidate_indexes(left_index, left_count, right_indexes):
    if not right_indexes:
        return []
    if left_count <= 1:
        target = 0
    else:
        target = round(left_index * (len(right_indexes) - 1) / (left_count - 1))
    return sorted(
        right_indexes,
        key=lambda right_index: (abs(right_index - target), right_index),
    )[:COMPARE_REPLACE_PAIR_CANDIDATES]


def compare_replace_similarity(left_text, right_text):
    matcher = SequenceMatcher(None, left_text, right_text, autojunk=False)
    if matcher.quick_ratio() < COMPARE_REPLACE_PAIR_QUICK_RATIO:
        return None
    similarity = matcher.ratio()
    if similarity < COMPARE_REPLACE_PAIR_MIN_RATIO:
        return None
    return similarity


def compare_replace_hunk(left_entries, right_entries, left_start, left_end, right_start, right_end):
    left_lines = compare_line_payloads(left_entries, left_start, left_end)
    right_lines = compare_line_payloads(right_entries, right_start, right_end)
    hunk = {
        "op": "replace",
        "left": {"start": left_start, "end": left_end, "lines": left_lines},
        "right": {"start": right_start, "end": right_end, "lines": right_lines},
        "changed_pairs": [],
        "left_unpaired": [],
        "right_unpaired": [],
    }
    unmatched_right = set(range(len(right_lines)))
    if len(left_lines) == 1 and len(right_lines) == 1:
        left_text = str(left_lines[0].get("text") or "")
        right_text = str(right_lines[0].get("text") or "")
        if max(len(left_text), len(right_text)) <= COMPARE_LINE_DISPLAY_TRUNCATE:
            left_segments, right_segments = changed_line_segments(left_text, right_text)
            pair = {
                "left_index": 0,
                "right_index": 0,
                "similarity": round(SequenceMatcher(None, left_text, right_text, autojunk=False).ratio(), 3),
                "segments": {"left": left_segments, "right": right_segments},
            }
            if compare_line_structural_changed(left_lines[0], right_lines[0]):
                pair["structural_change"] = True
                pair["structural"] = {
                    "left": compare_line_structural_payload(left_lines[0]),
                    "right": compare_line_structural_payload(right_lines[0]),
                }
            hunk["changed_pairs"].append(pair)
            return hunk

    for left_index, left_line in enumerate(left_lines):
        left_text = str(left_line.get("text") or "")
        if len(left_text) > COMPARE_LINE_DISPLAY_TRUNCATE:
            hunk["left_unpaired"].append(left_index)
            continue
        best = None
        for right_index in replace_pair_candidate_indexes(left_index, len(left_lines), unmatched_right):
            right_text = str(right_lines[right_index].get("text") or "")
            if len(right_text) > COMPARE_LINE_DISPLAY_TRUNCATE:
                continue
            similarity = compare_replace_similarity(left_text, right_text)
            if similarity is None:
                continue
            score = (similarity, -abs(right_index - left_index), -right_index)
            if best is None or score > best[0]:
                best = (score, similarity, right_index)
        if best is None:
            hunk["left_unpaired"].append(left_index)
            continue
        _, similarity, right_index = best
        unmatched_right.remove(right_index)
        right_text = str(right_lines[right_index].get("text") or "")
        left_segments, right_segments = changed_line_segments(left_text, right_text)
        pair = {
            "left_index": left_index,
            "right_index": right_index,
            "similarity": round(similarity, 3),
            "segments": {"left": left_segments, "right": right_segments},
        }
        if compare_line_structural_changed(left_line, right_lines[right_index]):
            pair["structural_change"] = True
            pair["structural"] = {
                "left": compare_line_structural_payload(left_line),
                "right": compare_line_structural_payload(right_lines[right_index]),
            }
        hunk["changed_pairs"].append(pair)

    hunk["right_unpaired"] = sorted(unmatched_right)
    hunk["changed_pairs"].sort(key=lambda item: item["left_index"])
    return hunk


def change_hunk_units(hunk):
    if hunk["op"] == "insert":
        return len(hunk["right"].get("lines", []))
    if hunk["op"] == "delete":
        return len(hunk["left"].get("lines", []))
    if hunk["op"] == "replace":
        return (
            2 * len(hunk.get("changed_pairs", []))
            + len(hunk.get("left_unpaired", []))
            + len(hunk.get("right_unpaired", []))
        )
    return 0


def change_hunk_line_counts(hunk):
    if hunk["op"] == "insert":
        right = len(hunk["right"].get("lines", []))
        return {"left": 0, "right": right, "total": right}
    if hunk["op"] == "delete":
        left = len(hunk["left"].get("lines", []))
        return {"left": left, "right": 0, "total": left}
    if hunk["op"] == "replace":
        paired = len(hunk.get("changed_pairs", []))
        left = paired + len(hunk.get("left_unpaired", []))
        right = paired + len(hunk.get("right_unpaired", []))
        return {"left": left, "right": right, "total": left + right}
    return {"left": 0, "right": 0, "total": 0}


def add_change_hunk_totals(totals, hunk):
    if hunk["op"] == "insert":
        totals["added_line_count"] += len(hunk["right"].get("lines", []))
    elif hunk["op"] == "delete":
        totals["removed_line_count"] += len(hunk["left"].get("lines", []))
    elif hunk["op"] == "replace":
        totals["changed_line_count"] += len(hunk.get("changed_pairs", []))
        totals["removed_line_count"] += len(hunk.get("left_unpaired", []))
        totals["added_line_count"] += len(hunk.get("right_unpaired", []))


def trim_change_hunk_to_budget(hunk, remaining_units):
    units = change_hunk_units(hunk)
    if units <= remaining_units:
        return hunk, units, {"left": 0, "right": 0, "total": 0}

    omitted = {"left": 0, "right": 0, "total": 0}

    def _omit(side):
        omitted[side] += 1
        omitted["total"] += 1

    if hunk["op"] == "insert":
        keep = max(0, remaining_units)
        lines = hunk["right"].get("lines", [])
        omitted_count = max(0, len(lines) - keep)
        hunk["right"]["lines"] = lines[:keep]
        omitted["right"] = omitted_count
        omitted["total"] = omitted_count
        if omitted_count:
            hunk["lines_omitted"] = omitted
        return hunk if keep else None, keep, omitted
    if hunk["op"] == "delete":
        keep = max(0, remaining_units)
        lines = hunk["left"].get("lines", [])
        omitted_count = max(0, len(lines) - keep)
        hunk["left"]["lines"] = lines[:keep]
        omitted["left"] = omitted_count
        omitted["total"] = omitted_count
        if omitted_count:
            hunk["lines_omitted"] = omitted
        return hunk if keep else None, keep, omitted

    while change_hunk_units(hunk) > remaining_units and hunk.get("left_unpaired"):
        hunk["left_unpaired"].pop()
        _omit("left")
    while change_hunk_units(hunk) > remaining_units and hunk.get("right_unpaired"):
        hunk["right_unpaired"].pop()
        _omit("right")
    while change_hunk_units(hunk) > remaining_units and hunk.get("changed_pairs"):
        hunk["changed_pairs"].pop()
        _omit("left")
        _omit("right")
    if omitted["total"]:
        hunk["lines_omitted"] = omitted
    units = change_hunk_units(hunk)
    return hunk if units else None, units, omitted


def hunk_line_diff(
    left_entries,
    right_entries,
    *,
    max_changed_lines=COMPARE_MAX_CHANGED_LINES,
    max_hunks=COMPARE_MAX_HUNKS,
    inline_context=COMPARE_INLINE_EQUAL_CONTEXT,
):
    use_line_index = _all_compare_entries_have_line_indexes(left_entries, right_entries)
    left_match_keys = [compare_line_sequence_key(entry, use_line_index=use_line_index) for entry in left_entries]
    right_match_keys = [compare_line_sequence_key(entry, use_line_index=use_line_index) for entry in right_entries]
    matcher = SequenceMatcher(None, left_match_keys, right_match_keys, autojunk=False)
    hunks = []
    totals = {
        "left_total_lines": len(left_entries),
        "right_total_lines": len(right_entries),
        "equal_line_count": 0,
        "changed_line_count": 0,
        "added_line_count": 0,
        "removed_line_count": 0,
    }
    lines_omitted = {"left": 0, "right": 0, "total": 0}
    hunks_omitted = 0
    emitted_change_units = 0
    emitted_change_hunks = 0

    for tag, left_start, left_end, right_start, right_end in matcher.get_opcodes():
        if tag == "equal":
            totals["equal_line_count"] += left_end - left_start
            hunks.append(compare_equal_hunk(
                left_entries,
                right_entries,
                left_start,
                left_end,
                right_start,
                right_end,
                inline_context,
            ))
            continue

        if tag == "insert":
            hunk = {
                "op": "insert",
                "left": {"start": left_start, "end": left_end},
                "right": {
                    "start": right_start,
                    "end": right_end,
                    "lines": compare_line_payloads(right_entries, right_start, right_end),
                },
            }
        elif tag == "delete":
            hunk = {
                "op": "delete",
                "left": {
                    "start": left_start,
                    "end": left_end,
                    "lines": compare_line_payloads(left_entries, left_start, left_end),
                },
                "right": {"start": right_start, "end": right_end},
            }
        else:
            hunk = compare_replace_hunk(left_entries, right_entries, left_start, left_end, right_start, right_end)
        hunk = compare_hunk_severity_kind(hunk)

        if emitted_change_hunks >= max_hunks or emitted_change_units >= max_changed_lines:
            hunks_omitted += 1
            omitted = change_hunk_line_counts(hunk)
            lines_omitted["left"] += omitted["left"]
            lines_omitted["right"] += omitted["right"]
            lines_omitted["total"] += omitted["total"]
            continue
        remaining_units = max_changed_lines - emitted_change_units
        hunk, used_units, omitted = trim_change_hunk_to_budget(hunk, remaining_units)
        if hunk is None:
            hunks_omitted += 1
            lines_omitted["left"] += omitted["left"]
            lines_omitted["right"] += omitted["right"]
            lines_omitted["total"] += omitted["total"]
            continue
        lines_omitted["left"] += omitted["left"]
        lines_omitted["right"] += omitted["right"]
        lines_omitted["total"] += omitted["total"]
        add_change_hunk_totals(totals, hunk)
        hunks.append(hunk)
        emitted_change_hunks += 1
        emitted_change_units += used_units

    return {
        "hunks": hunks,
        "totals": totals,
        "truncated": {
            "hunks_omitted": hunks_omitted,
            "lines_omitted": lines_omitted,
        },
    }


def _hunk_density_counts(hunk):
    if hunk["op"] == "equal":
        return [("equal", max(0, int(hunk["left"]["end"]) - int(hunk["left"]["start"])))]
    if hunk["op"] == "insert":
        return [("added", len(hunk["right"].get("lines", [])))]
    if hunk["op"] == "delete":
        return [("removed", len(hunk["left"].get("lines", [])))]
    if hunk["op"] == "replace":
        return [
            ("changed", len(hunk.get("changed_pairs", []))),
            ("removed", len(hunk.get("left_unpaired", []))),
            ("added", len(hunk.get("right_unpaired", []))),
        ]
    return []


def density_bucket_tone(bucket):
    changed = int(bucket.get("changed") or 0)
    added = int(bucket.get("added") or 0)
    removed = int(bucket.get("removed") or 0)
    equal = int(bucket.get("equal") or 0)
    if changed:
        return "changed"
    if added or removed:
        if added > removed:
            return "added"
        return "removed"
    if equal:
        return "equal"
    return ""


def density_buckets_for_hunks(hunks, bucket_count=COMPARE_MINIMAP_BUCKETS):
    bucket_count = max(1, int(bucket_count or COMPARE_MINIMAP_BUCKETS))
    units = []
    for hunk in hunks:
        for category, count in _hunk_density_counts(hunk):
            units.extend([category] * max(0, int(count or 0)))
    total_units = len(units)
    buckets = [
        {
            "start": (index * total_units) // bucket_count if total_units else 0,
            "end": ((index + 1) * total_units) // bucket_count if total_units else 0,
            "equal": 0,
            "added": 0,
            "removed": 0,
            "changed": 0,
        }
        for index in range(bucket_count)
    ]
    if not total_units:
        return buckets
    for position, category in enumerate(units):
        bucket_index = min(bucket_count - 1, (position * bucket_count) // total_units)
        buckets[bucket_index][category] += 1
    return buckets


def compare_deltas(left_run, right_run, left_finding_count, right_finding_count):
    left_duration = run_duration_seconds(left_run)
    right_duration = run_duration_seconds(right_run)
    left_lines = int(left_run.get("output_line_count") or 0)
    right_lines = int(right_run.get("output_line_count") or 0)
    return {
        "exit_code_changed": left_run.get("exit_code") != right_run.get("exit_code"),
        "exit_code": {"left": left_run.get("exit_code"), "right": right_run.get("exit_code")},
        "duration_seconds": {
            "left": left_duration,
            "right": right_duration,
            "delta": None if left_duration is None or right_duration is None else right_duration - left_duration,
        },
        "output_lines": {
            "left": left_lines,
            "right": right_lines,
            "delta": right_lines - left_lines,
        },
        "findings": {
            "left": left_finding_count,
            "right": right_finding_count,
            "delta": right_finding_count - left_finding_count,
        },
    }


_compare_replace_hunk = compare_replace_hunk
_hunk_line_diff = hunk_line_diff
