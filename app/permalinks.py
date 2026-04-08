"""
Permalink page rendering — styled HTML pages for run history and tab snapshots.
"""

import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Response, has_request_context, render_template, request

from config import CFG, DARK_THEME, LIGHT_THEME, theme_css_vars

_FONT_DIR = Path(__file__).resolve().parent / "static" / "fonts"
_FONT_FILES = [
    ("JetBrains Mono", 300, "JetBrainsMono-300.ttf"),
    ("JetBrains Mono", 400, "JetBrainsMono-400.ttf"),
    ("JetBrains Mono", 700, "JetBrainsMono-700.ttf"),
    ("Syne", 700, "Syne-700.ttf"),
    ("Syne", 800, "Syne-800.ttf"),
]


def _font_face_css(*, embed: bool = False) -> str:
    rules = []
    for family, weight, filename in _FONT_FILES:
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


def _current_theme() -> str:
    """Return the current session theme if available, otherwise default to dark."""
    if not has_request_context():
        return "dark"
    try:
        return "light" if request.cookies.get("pref_theme") == "light" else "dark"
    except Exception:
        return "dark"


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


def _normalize_permalink_lines(content_lines, label: str):
    content_items = list(content_lines or [])
    is_structured_snapshot = any(isinstance(entry, dict) for entry in content_items)
    normalized_lines = []

    if is_structured_snapshot:
        has_prompt_echo = any(
            isinstance(entry, dict) and str(entry.get("cls", "")) == "prompt-echo"
            for entry in content_items
        )
        if not has_prompt_echo:
            normalized_lines.append({"text": f"$ {label}", "cls": "prompt-echo", "tsC": "", "tsE": ""})
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
        normalized_lines.append({"text": f"$ {label}", "cls": "prompt-echo", "tsC": "", "tsE": ""})
        normalized_lines.append({"text": "", "cls": "", "tsC": "", "tsE": ""})
        for entry in content_items:
            normalized_lines.append({"text": str(entry), "cls": "", "tsC": "", "tsE": ""})

    return normalized_lines


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


def _permalink_context(title, label, created, content_lines, json_url, extra_actions=None):
    app_name = CFG.get("app_name", "shell.darklab.sh")
    theme_class = "light" if _current_theme() == "light" else ""
    normalized_lines = _normalize_permalink_lines(content_lines, label)
    has_timestamp_metadata = any(line.get("tsC") or line.get("tsE") for line in normalized_lines)
    created_fmt = created[:19].replace("T", " ") + " UTC"

    return {
        "page_title": f"{app_name} — {title}",
        "app_name": app_name,
        "theme_class": theme_class,
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
        "dark_theme_css": theme_css_vars(DARK_THEME),
        "light_theme_css": theme_css_vars(LIGHT_THEME),
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
    app_name = CFG.get("app_name", "shell.darklab.sh")
    html = render_template(
        "permalink_error.html",
        page_title=f"{app_name} — {noun} not found",
        app_name=app_name,
        theme_class="light" if _current_theme() == "light" else "",
        dark_theme_css=theme_css_vars(DARK_THEME),
        light_theme_css=theme_css_vars(LIGHT_THEME),
        noun=noun,
        detail=detail,
    )
    return Response(html, status=404, mimetype="text/html")


def _permalink_page(title, label, created, content_lines, json_url, extra_actions=None) -> Response:
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
        ),
    )
    return Response(html, mimetype="text/html")
