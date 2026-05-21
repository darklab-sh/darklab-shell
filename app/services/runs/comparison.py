"""Shared run comparison helpers for history and project responses."""

import json
import re
from collections import Counter
from datetime import datetime
from difflib import SequenceMatcher

from core.output_signals import (
    classify_line,
    command_root as output_command_root,
    extract_target,
    strip_ansi_codes,
)
from services.runs.output_model import line_event_from_legacy, to_legacy_entry
from services.runs.output_store import load_full_output_entries

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


def preview_output_entries_from_run(run):
    raw = run.get("output_preview")
    if raw is None:
        raw = run.get("output")
    loaded = json.loads(raw) if raw else []
    if loaded and isinstance(loaded[0], str):
        return [to_legacy_entry(line_event_from_legacy(line)) for line in loaded]
    entries = []
    for item in loaded:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            entry = to_legacy_entry(
                line_event_from_legacy(
                    item["text"],
                    item.get("cls", ""),
                    ts_clock=item.get("tsC", ""),
                    ts_elapsed=item.get("tsE", ""),
                    signals=item.get("signals") if isinstance(item.get("signals"), list) else None,
                    line_index=item.get("line_index"),
                    command_root=item.get("command_root", ""),
                    target=item.get("target", ""),
                    entities=item.get("entities") if isinstance(item.get("entities"), list) else None,
                )
            )
            if isinstance(item.get("signals"), list):
                entry["signals"] = [str(signal) for signal in item["signals"] if str(signal)]
            if isinstance(item.get("line_index"), int):
                entry["line_index"] = item["line_index"]
            if isinstance(item.get("command_root"), str):
                entry["command_root"] = item["command_root"]
            if isinstance(item.get("target"), str):
                entry["target"] = item["target"]
            entries.append(entry)
        elif isinstance(item, str):
            entries.append(to_legacy_entry(line_event_from_legacy(item)))
    return entries


def compare_full_output_entries(run):
    if run.get("full_output_available") and run.get("rel_path"):
        return load_full_output_entries(run["rel_path"]), "full", bool(run.get("full_output_truncated"))
    return preview_output_entries_from_run(run), "preview", bool(run.get("preview_truncated"))


def is_compare_chrome_line(entry, text):
    cls = str(entry.get("cls", "")) if isinstance(entry, dict) else ""
    stripped = str(text or "").strip()
    if not stripped:
        return True
    if cls == "prompt-echo":
        return True
    if re.match(r"^\[(?:process exited with code|history\s+—\s+exit)\b", stripped, re.I):
        return True
    return False


def line_entry_text(entry):
    if isinstance(entry, dict):
        return str(entry.get("text", ""))
    return str(entry or "")


def compare_entries_for_diff(run):
    entries, source, partial = compare_full_output_entries(run)
    compared = []
    byte_count = 0
    truncated_by_limit = False
    for entry in entries:
        text = line_entry_text(entry).rstrip("\n")
        if is_compare_chrome_line(entry, text):
            continue
        encoded_len = len(text.encode("utf-8", errors="replace"))
        if len(compared) >= COMPARE_MAX_LINES or byte_count + encoded_len > COMPARE_MAX_BYTES:
            truncated_by_limit = True
            break
        compared.append({
            "text": text,
            "line_index": entry.get("line_index") if isinstance(entry, dict) else None,
            "signals": entry.get("signals", []) if isinstance(entry, dict) else [],
        })
        byte_count += encoded_len
    return compared, {
        "source": source,
        "partial": partial or truncated_by_limit,
        "truncated_by_limit": truncated_by_limit,
        "compared_lines": len(compared),
        "max_lines": COMPARE_MAX_LINES,
        "max_bytes": COMPARE_MAX_BYTES,
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
    return {
        "text": str(entry.get("text") or ""),
        "line_index": entry.get("line_index"),
    }


def compare_line_payloads(entries, start, end):
    return [compare_line_payload(entry) for entry in entries[start:end]]


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
            hunk["changed_pairs"].append({
                "left_index": 0,
                "right_index": 0,
                "similarity": round(SequenceMatcher(None, left_text, right_text, autojunk=False).ratio(), 3),
                "segments": {"left": left_segments, "right": right_segments},
            })
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
        hunk["changed_pairs"].append({
            "left_index": left_index,
            "right_index": right_index,
            "similarity": round(similarity, 3),
            "segments": {"left": left_segments, "right": right_segments},
        })

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
    left_texts = [str(entry.get("text") or "") for entry in left_entries]
    right_texts = [str(entry.get("text") or "") for entry in right_entries]
    matcher = SequenceMatcher(None, left_texts, right_texts, autojunk=False)
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
