"""
Permalink page rendering — styled HTML pages for run history and tab snapshots.
"""

import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Response, render_template

from config import (
    CFG,
    DARK_THEME,
    THEME_REGISTRY,
    get_theme_entry,
    theme_runtime_css_vars,
)
from helpers import FONT_FILES, current_theme_name

_FONT_DIR = Path(__file__).resolve().parent / "static" / "fonts"


def _font_face_css(*, embed: bool = False) -> str:
    # Downloaded HTML can either reference app-hosted font files or embed them
    # directly so the export stays portable offline.
    rules = []
    for family, weight, filename in FONT_FILES:
        font_path = _FONT_DIR / filename
        if embed:
            try:
                data = base64.b64encode(font_path.read_bytes()).decode("ascii")
                src = f"url(data:font/ttf;base64,{data}) format('truetype')"
            except OSError:
                continue
        else:
            src = f"url('/vendor/fonts/{filename}') format('truetype')"
        rules.append(
            "@font-face {"
            f" font-family: '{family}';"
            " font-style: normal;"
            f" font-weight: {weight};"
            " font-display: swap;"
            f" src: {src};"
            " }"
        )
    return "\n".join(rules)


def _format_retention(days: int) -> str:
    """Return a human-friendly retention description."""
    if days == 0:
        return "unlimited — snapshots are never automatically deleted"

    def _unit(n: int, singular: str) -> str:
        return f"{n} {singular}{'s' if n != 1 else ''}"

    years, r = divmod(days, 365)
    months, rem = divmod(r, 30)
    parts = []
    if years:
        parts.append(_unit(years, "year"))
    if months:
        parts.append(_unit(months, "month"))
    if rem:
        parts.append(_unit(rem, "day"))
    if not parts:
        parts = [_unit(days, "day")]

    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def _prompt_echo_text(label: str) -> str:
    # Single server-side source of truth for prompt-echo text on synthesized
    # history/snapshot lines. Reads CFG["prompt_prefix"] so permalinks render
    # the full configured prefix (e.g. "anon@darklab:~$ ls -la") rather than a
    # reduced "$ ls -la" echo that drifts from the live shell. Paired with the
    # JS export helper (ExportHtmlUtils.renderExportPromptEcho) that consumes
    # this text by splitting on its first space to colorize the prefix.
    prefix = str(CFG.get("prompt_prefix", "$")).strip() or "$"
    return f"{prefix} {label}".rstrip()


def _normalize_permalink_lines(content_lines, label: str):
    # History pages, share pages, and HTML exports feed slightly different line
    # shapes into this layer; normalize them once for the shared template.
    content_items = list(content_lines or [])
    is_structured_snapshot = any(isinstance(entry, dict) for entry in content_items)
    normalized_lines = []
    echo_text = _prompt_echo_text(label)

    if is_structured_snapshot:
        has_prompt_echo = any(
            isinstance(entry, dict)
            and str(entry.get("cls", "")) == "prompt-echo"
            and len(str(entry.get("text", "")).split(None, 1)) > 1
            for entry in content_items
        )
        if not has_prompt_echo:
            normalized_lines.append({"text": echo_text, "cls": "prompt-echo", "tsC": "", "tsE": ""})
            normalized_lines.append({"text": "", "cls": "", "tsC": "", "tsE": ""})
        for entry in content_items:
            if isinstance(entry, str):
                normalized_lines.append({"text": entry, "cls": "", "tsC": "", "tsE": ""})
            else:
                normalized_lines.append({
                    "text": str(entry.get("text", "")),
                    "cls": str(entry.get("cls", "")),
                    "tsC": str(entry.get("tsC", "")),
                    "tsE": str(entry.get("tsE", "")),
                })
    else:
        normalized_lines.append({"text": echo_text, "cls": "prompt-echo", "tsC": "", "tsE": ""})
        normalized_lines.append({"text": "", "cls": "", "tsC": "", "tsE": ""})
        for entry in content_items:
            normalized_lines.append({"text": str(entry), "cls": "", "tsC": "", "tsE": ""})

    return normalized_lines


def _format_duration(started: str, finished: str) -> str | None:
    """Return a human-readable elapsed duration string, or None on any error."""
    try:
        t0 = datetime.fromisoformat(started.replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(finished.replace("Z", "+00:00"))
        s = max(0.0, (t1 - t0).total_seconds())
        if s < 60:
            return f"{s:.1f}s"
        minutes, secs = divmod(int(s), 60)
        if minutes < 60:
            return f"{minutes}m {secs:02d}s"
        hours, mins = divmod(minutes, 60)
        return f"{hours}h {mins:02d}m {secs:02d}s"
    except Exception:
        return None


def _expiry_note(created: str) -> str:
    """Return an HTML snippet showing how long until this permalink expires."""
    retention = CFG.get("permalink_retention_days", 0)
    if not retention:
        return ""
    try:
        created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        if created_dt.tzinfo is None:
            created_dt = created_dt.replace(tzinfo=timezone.utc)
        expiry_dt = created_dt + timedelta(days=retention)
        remaining = expiry_dt - datetime.now(timezone.utc)
        days_left = remaining.days
        if remaining.total_seconds() <= 0:
            return ""
        expiry_date = expiry_dt.strftime("%Y-%m-%d")
        label = "expires today" if days_left == 0 else f"expires in {_format_retention(days_left)}"
        return (
            f'<div class="meta expiry" title="Expires {expiry_date}">'
            f'{label} &nbsp;·&nbsp; {expiry_date}'
            f'</div>'
        )
    except Exception:
        return ""


def _permalink_context(title, label, created, content_lines, json_url, extra_actions=None, meta=None):
    # Build one context shape for both live responses and downloadable HTML so
    # metadata/actions stay in sync across both surfaces.
    app_name = CFG.get("app_name", "darklab shell")
    theme_entry = get_theme_entry(current_theme_name(), fallback=CFG.get("default_theme", "darklab_obsidian.yaml"))
    normalized_lines = _normalize_permalink_lines(content_lines, label)
    has_timestamp_metadata = any(line.get("tsC") or line.get("tsE") for line in normalized_lines)
    created_fmt = created[:19].replace("T", " ") + " UTC"

    return {
        "page_title": f"{app_name} — {title}",
        "app_name": app_name,
        "current_theme": theme_entry,
        "current_theme_css": theme_entry["vars"],
        "theme_registry": {"current": theme_entry, "themes": THEME_REGISTRY},
        "label": label,
        "created_fmt": created_fmt,
        "created_json": json.dumps(created),
        "expiry_html": _expiry_note(created),
        "json_url": json_url,
        "extra_actions": extra_actions or [],
        "lines_json": json.dumps(normalized_lines),
        "has_timestamp_metadata": has_timestamp_metadata,
        "toggle_ts_disabled": not has_timestamp_metadata,
        "app_name_json": json.dumps(app_name),
        "label_json": json.dumps(label),
        "font_faces_css": _font_face_css(embed=True),
        "fallback_theme_css": theme_runtime_css_vars(DARK_THEME),
        "meta": meta,
        "meta_json": json.dumps(meta),
    }


def _permalink_error_page(noun: str) -> Response:
    """Render a themed 404 page for a missing permalink (snapshot or run)."""
    retention = CFG.get("permalink_retention_days", 0)
    retention_str = _format_retention(retention)
    if retention == 0:
        detail = (
            f"The {noun} ID is invalid, the {noun} was never saved, "
            f"or it was manually deleted."
        )
    else:
        detail = (
            f"The {noun} ID is invalid, it was manually deleted, or it was "
            f"automatically deleted after exceeding the configured retention "
            f"period ({retention_str})."
        )
    app_name = CFG.get("app_name", "darklab shell")
    current_theme = get_theme_entry(current_theme_name(), fallback=CFG.get("default_theme", "darklab_obsidian.yaml"))
    html = render_template(
        "permalink_error.html",
        page_title=f"{app_name} — {noun} not found",
        app_name=app_name,
        current_theme=current_theme,
        current_theme_css=current_theme["vars"],
        theme_registry={"current": current_theme, "themes": THEME_REGISTRY},
        fallback_theme_css=theme_runtime_css_vars(DARK_THEME),
        noun=noun,
        detail=detail,
    )
    return Response(html, status=404, mimetype="text/html")


def _permalink_page(title, label, created, content_lines, json_url, extra_actions=None, meta=None) -> Response:
    """Render a themed HTML page for a permalink."""
    html = render_template(
        "permalink.html",
        **_permalink_context(
            title=title,
            label=label,
            created=created,
            content_lines=content_lines,
            json_url=json_url,
            extra_actions=extra_actions,
            meta=meta,
        ),
    )
    return Response(html, mimetype="text/html")
