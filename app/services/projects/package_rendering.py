"""
Evidence package rendering and export helpers.
"""

from __future__ import annotations

import gzip
import html
import json
import re
from pathlib import PurePosixPath

from core.redaction import redact_line_entries
from services.history.permalinks import _font_face_css, _format_duration, _permalink_context
from services.projects.contracts import ProjectWorkspaceError
from services.projects.models import entity_note_body as _entity_note_body
from services.projects.packages import (
    redact_package_run as _redact_package_run,
    redact_package_value as _redact_package_value,
)
from services.projects.utils import cfg_int as _cfg_int
from services.runs.output_store import load_full_output_entries


def _package_zip_artifact_path(workspace_path, used_paths):
    parts = [
        part for part in PurePosixPath(str(workspace_path or "").replace("\\", "/")).parts
        if part not in {"", ".", ".."}
    ]
    relative = "/".join(parts) or "artifact"
    candidate = f"artifacts/{relative}"
    if candidate not in used_paths:
        used_paths.add(candidate)
        return candidate
    stem = PurePosixPath(relative).stem or "artifact"
    suffix = PurePosixPath(relative).suffix
    parent = str(PurePosixPath(relative).parent)
    prefix = "" if parent in {"", "."} else f"{parent}/"
    for index in range(2, 1000):
        candidate = f"artifacts/{prefix}{stem}-{index}{suffix}"
        if candidate not in used_paths:
            used_paths.add(candidate)
            return candidate
    raise ProjectWorkspaceError("could not allocate artifact package path")


def _package_html_escape(value):
    return html.escape("" if value is None else str(value), quote=True)


def _package_short_id(value):
    text = str(value or "")
    return text[:12] if len(text) > 12 else text


def _package_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _package_markdown_text(value):
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\n", " ").strip()
    return re.sub(r"([\\`*_{}\[\]<>()#+!|])", r"\\\1", text)


def _package_markdown_code(value):
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\n", " ").strip()
    if not text:
        return "``"
    text = text.replace("|", "\\|")
    longest_tick = max((len(match.group(0)) for match in re.finditer(r"`+", text)), default=0)
    fence = "`" * (longest_tick + 1)
    return f"{fence}{text}{fence}" if longest_tick == 0 else f"{fence} {text} {fence}"


def _package_markdown_link(label, href):
    safe_label = _package_markdown_text(label) or "link"
    safe_href = str(href or "").replace(")", "%29").replace(" ", "%20")
    return f"[{safe_label}]({safe_href})" if safe_href else safe_label


def _package_output_entry(item) -> dict[str, object]:
    if isinstance(item, dict) and isinstance(item.get("text"), str):
        entry = {
            "text": item["text"],
            "cls": str(item.get("cls", "")),
            "tsC": str(item.get("tsC", "")),
            "tsE": str(item.get("tsE", "")),
        }
        if isinstance(item.get("signals"), list):
            entry["signals"] = [str(signal) for signal in item["signals"] if str(signal)]
        if isinstance(item.get("line_index"), int):
            entry["line_index"] = item["line_index"]
        if isinstance(item.get("command_root"), str):
            entry["command_root"] = item["command_root"]
        if isinstance(item.get("target"), str):
            entry["target"] = item["target"]
        return entry
    return {"text": str(item or ""), "cls": "", "tsC": "", "tsE": ""}


def _package_preview_output_entries(run) -> list[dict[str, object]]:
    raw = run.get("output_preview")
    if raw is None:
        raw = run.get("output")
    if not raw:
        return []
    try:
        loaded = json.loads(raw)
    except (TypeError, ValueError):
        return [{"text": line, "cls": "", "tsC": "", "tsE": ""} for line in str(raw).splitlines()]
    if not isinstance(loaded, list):
        return [{"text": str(loaded), "cls": "", "tsC": "", "tsE": ""}]
    return [_package_output_entry(item) for item in loaded]


def _package_run_rows(conn, session_id, run_ids):
    ids = [str(run_id) for run_id in run_ids if run_id]
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        "SELECT r.*, art.rel_path "  # nosec
        "FROM runs r LEFT JOIN run_output_artifacts art ON art.run_id = r.id "
        f"WHERE r.session_id = ? AND r.id IN ({placeholders})",
        [session_id, *ids],
    ).fetchall()
    by_id = {str(row["id"]): dict(row) for row in rows}
    return [by_id[run_id] for run_id in ids if run_id in by_id]


def _package_run_output_entries(run, *, cfg=None, include_companion=False):
    if run.get("full_output_available") and run.get("rel_path"):
        try:
            entries = load_full_output_entries(str(run["rel_path"]))
        except (OSError, gzip.BadGzipFile, EOFError, ValueError):
            entries = _package_preview_output_entries(run)
        if run.get("full_output_truncated"):
            entries.append({
                "text": "[full output truncated by the server-side capture limit]",
                "cls": "warn",
                "tsC": "",
                "tsE": "",
            })
    else:
        entries = _package_preview_output_entries(run)
        if run.get("preview_truncated"):
            entries.append({
                "text": "[preview truncated; full output was not available for this package export]",
                "cls": "warn",
                "tsC": "",
                "tsE": "",
            })

    max_lines = _cfg_int("max_output_lines", 5000, cfg=cfg) or 5000
    if len(entries) > max_lines:
        hidden = len(entries) - max_lines
        companion_entries = list(entries)
        capped_entries: list[dict[str, object]] = list(entries[:max_lines])
        cap_notice: dict[str, object] = {
            "text": f"[package transcript capped at {max_lines} lines; {hidden} additional lines omitted]",
            "cls": "warn",
            "tsC": "",
            "tsE": "",
        }
        capped_entries.append(cap_notice)
        if include_companion:
            return capped_entries, companion_entries, cap_notice
        return capped_entries
    if include_companion:
        return entries, [], None
    return entries


def _package_run_text_bytes(entries, redaction_rules=None):
    entries = redact_line_entries(entries, redaction_rules) if redaction_rules else entries
    lines = []
    for entry in entries:
        if isinstance(entry, dict):
            lines.append(str(entry.get("text") or ""))
        else:
            lines.append(str(entry or ""))
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def _package_css():
    return (
        "/* darklab shell evidence package CSS snapshot: package_format_version=1 */\n"
        + _font_face_css(embed=True)
        + "\n"
        + """
:root {
  color-scheme: dark;
  --bg: #0f1215;
  --panel: #171c20;
  --panel-2: #20272d;
  --text: #e6edf3;
  --muted: #9da9b5;
  --accent: #54d18a;
  --border: #303a43;
  --danger: #ff7b72;
  --warn: #f2c94c;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.5;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.page { width: min(1180px, calc(100vw - 32px)); margin: 0 auto; padding: 32px 0 48px; }
.topline { color: var(--muted); font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.08em; }
h1, h2, h3 { margin: 0; line-height: 1.2; }
h1 { margin-top: 8px; font-size: clamp(2rem, 5vw, 3.7rem); }
h2 { margin: 32px 0 12px; font-size: 1.15rem; }
.subtitle { max-width: 780px; margin: 12px 0 0; color: var(--muted); }
.grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); margin-top: 24px; }
.metric, .card, .transcript {
  border: 1px solid var(--border);
  background: var(--panel);
  border-radius: 8px;
}
.metric { padding: 14px; }
.metric strong { display: block; font-size: 1.6rem; }
.metric span { color: var(--muted); font-size: 0.88rem; }
.card { padding: 16px; margin-top: 12px; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--panel-2);
  color: var(--text);
  font-size: 0.82rem;
  padding: 4px 9px;
}
table { width: 100%; border-collapse: collapse; overflow-wrap: anywhere; }
th, td { padding: 10px 8px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }
th { color: var(--muted); font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em; }
button.table-sort {
  appearance: none;
  border: 0;
  padding: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  letter-spacing: inherit;
  text-transform: inherit;
  cursor: pointer;
}
button.table-sort::after { content: " ↕"; color: var(--muted); }
button.table-sort[aria-sort="ascending"]::after { content: " ↑"; color: var(--accent); }
button.table-sort[aria-sort="descending"]::after { content: " ↓"; color: var(--accent); }
blockquote { margin: 8px 0 0; padding-left: 10px; border-left: 2px solid var(--border); color: var(--muted); }
.muted { color: var(--muted); }
.warn { color: var(--warn); }
.fail { color: var(--danger); }
.mono, .transcript {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
}
.run-list { list-style: none; padding: 0; margin: 0; display: grid; gap: 10px; }
.run-list li { border: 1px solid var(--border); border-radius: 8px; padding: 12px; background: var(--panel); }
.run-meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; color: var(--muted); font-size: 0.84rem; }
.transcript { padding: 16px; overflow: auto; white-space: pre-wrap; }
.line { min-height: 1.35em; }
.prompt-echo { color: var(--accent); }
.line.warn { color: var(--warn); }
.line:target { background: color-mix(in srgb, var(--accent) 18%, transparent); outline: 1px solid var(--accent); }
.footer { margin-top: 36px; color: var(--muted); font-size: 0.84rem; }
@media (max-width: 720px) {
  .page { width: min(100vw - 20px, 1180px); padding-top: 20px; }
  th:nth-child(4), td:nth-child(4) { display: none; }
}
""".strip()
    )


def _package_page(title, body, script="", *, css_href="assets/package.css"):
    css_tag = (
        f"<link rel=\"stylesheet\" href=\"{_package_html_escape(css_href)}\">\n"
        if css_href else f"<style>{_package_css()}</style>\n"
    )
    return (
        "<!doctype html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<meta name=\"darklab-package-format\" content=\"1\">\n"
        f"<title>{_package_html_escape(title)}</title>\n"
        f"{css_tag}"
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        f"{script}\n"
        "</body>\n"
        "</html>\n"
    )


def _render_package_run_html(
    run,
    entries,
    manifest,
    generated_at,
    *,
    transcript_text_path="",
    redaction_rules=None,
):
    entries = redact_line_entries(entries, redaction_rules) if redaction_rules else entries
    run = _redact_package_run(run, redaction_rules)
    command = str(run.get("command") or "")
    started = str(run.get("started") or "")
    finished = str(run.get("finished") or "")
    duration = _format_duration(started, finished)
    output_line_count = run.get("output_line_count")
    line_count = output_line_count if isinstance(output_line_count, int) else len(entries)
    if isinstance(output_line_count, str) and output_line_count.isdecimal():
        line_count = int(output_line_count)
    meta = {
        "exit_code": run.get("exit_code"),
        "duration": duration,
        "lines": f"{line_count:,} lines",
        "artifact_count": run.get("artifact_count") or 0,
        "finding_count": run.get("finding_count") or 0,
        "label_count": run.get("label_count") or 0,
        "note_count": run.get("note_count") or 0,
    }
    permalink_model = _permalink_context(
        title=command or str(run.get("id") or "Run transcript"),
        label=command,
        created=started or generated_at,
        content_lines=entries,
        json_url="../manifest.json",
        extra_actions=[],
        meta=meta,
    )["page_model"]
    normalized = permalink_model["transcript"]["lines"]
    rendered_lines = []
    for index, entry in enumerate(normalized, start=1):
        text = _package_html_escape(entry.get("text", "") if isinstance(entry, dict) else entry)
        cls = str(entry.get("cls", "") if isinstance(entry, dict) else "")
        line_index = entry.get("line_index") if isinstance(entry, dict) else None
        anchor = f" id=\"L{line_index + 1}\"" if isinstance(line_index, int) else f" id=\"line-{index}\""
        cls_attr = f" line {_package_html_escape(cls)}".strip()
        rendered_lines.append(f"<div{anchor} class=\"{cls_attr}\">{text}</div>")
    if not rendered_lines:
        rendered_lines.append("<div class=\"line muted\">No output captured.</div>")

    header = permalink_model.get("header", {})
    raw_metric_items = header.get("runMetaItems") if isinstance(header, dict) else []
    metric_items = raw_metric_items if isinstance(raw_metric_items, list) else []
    metric_html = "".join(
        "<div class=\"metric\">"
        f"<span>{_package_html_escape(item.get('kind') or 'item')}</span>"
        f"<strong>{_package_html_escape(item.get('text') or '')}</strong>"
        "</div>"
        for item in metric_items
        if isinstance(item, dict)
    )
    if not metric_html:
        metric_html = "".join(
            "<div class=\"metric\">"
            f"<span>{_package_html_escape(label)}</span>"
            f"<strong>{_package_html_escape(value)}</strong>"
            "</div>"
            for label, value in [
                ("Started", started or "unknown"),
                ("Finished", finished or "unknown"),
                ("Duration", duration or "unknown"),
                ("Lines", line_count),
            ]
        )
    project_name = (
        manifest.get("project", {}).get("name", "Project")
        if isinstance(manifest.get("project"), dict)
        else "Project"
    )
    run_id_text = _package_html_escape(run.get("id"))
    transcript_text_link = (
        f"<p><a href=\"../{_package_html_escape(transcript_text_path)}\">"
        "Download full text transcript</a></p>"
        if transcript_text_path else ""
    )
    body = (
        "<main class=\"page\">"
        f"<a href=\"../index.html\">Back to package index</a>"
        f"<div class=\"topline\">{_package_html_escape(project_name)} evidence package</div>"
        f"<h1>{_package_html_escape(command or run.get('id'))}</h1>"
        f"<p class=\"subtitle mono\">Run {run_id_text} · generated {_package_html_escape(generated_at)}</p>"
        f"<section class=\"grid\">{metric_html}</section>"
        "<h2>Transcript</h2>"
        f"{transcript_text_link}"
        f"<section class=\"transcript\">{''.join(rendered_lines)}</section>"
        "<p class=\"footer\">Generated by darklab shell evidence packages.</p>"
        "</main>"
    )
    return _package_page(command or "Run transcript", body, css_href="../assets/package.css")


def _finding_run_anchor(finding):
    run_id = str(finding.get("run_id") or "")
    line_number = finding.get("line_number")
    if isinstance(line_number, int):
        return f"runs/{_package_html_escape(run_id)}.html#L{line_number + 1}"
    return f"runs/{_package_html_escape(run_id)}.html"


def _package_finding_metadata_html(finding):
    labels = finding.get("labels") if isinstance(finding.get("labels"), list) else []
    note = finding.get("note") if isinstance(finding.get("note"), dict) else None
    pieces = []
    if labels:
        label_html = "".join(
            f"<span class=\"chip\">{_package_html_escape(label.get('label') or '')}</span>"
            for label in labels
            if isinstance(label, dict)
        )
        pieces.append(f"<div class=\"chips\">{label_html}</div>")
    if note:
        pieces.append(
            "<blockquote>"
            f"{_package_html_escape(note.get('body') or '')}"
            "</blockquote>"
        )
    return "".join(pieces)


def _package_finding_metadata_markdown(finding):
    labels = finding.get("labels") if isinstance(finding.get("labels"), list) else []
    note = finding.get("note") if isinstance(finding.get("note"), dict) else None
    parts = []
    label_values = [
        _package_markdown_code(label.get("label") or "")
        for label in labels
        if isinstance(label, dict) and label.get("label")
    ]
    if label_values:
        parts.append("Labels: " + ", ".join(label_values))
    if note and note.get("body"):
        parts.append("Note: " + _package_markdown_text(note.get("body") or ""))
    return "<br>" + "<br>".join(parts) if parts else ""


def _package_index_sort_script():
    return """
<script>
(() => {
  const table = document.querySelector("[data-sort-table='findings']");
  if (!table) return;
  const body = table.querySelector("tbody");
  if (!body) return;
  const buttons = table.querySelectorAll("[data-sort-key]");
  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.sortKey;
      const current = button.getAttribute("aria-sort");
      const direction = current === "ascending" ? "descending" : "ascending";
      buttons.forEach((item) => item.removeAttribute("aria-sort"));
      button.setAttribute("aria-sort", direction);
      const rows = Array.from(body.querySelectorAll("tr[data-finding-row]"));
      rows.sort((left, right) => {
        const leftValue = left.dataset[key] || "";
        const rightValue = right.dataset[key] || "";
        const result = leftValue.localeCompare(rightValue, undefined, { numeric: true, sensitivity: "base" });
        return direction === "ascending" ? result : -result;
      });
      rows.forEach((row) => body.appendChild(row));
    });
  });
})();
</script>
""".strip()


def _render_package_index_html(
    package,
    manifest,
    generated_at,
    run_pages,
    run_text_paths,
    artifact_paths,
    skipped_items,
):
    project = manifest.get("project") if isinstance(manifest.get("project"), dict) else {}
    counts = manifest.get("counts") if isinstance(manifest.get("counts"), dict) else {}
    targets = manifest.get("targets") if isinstance(manifest.get("targets"), list) else []
    runs = manifest.get("runs") if isinstance(manifest.get("runs"), list) else []
    findings = manifest.get("findings") if isinstance(manifest.get("findings"), list) else []
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), list) else []

    metric_html = "".join(
        "<div class=\"metric\">"
        f"<span>{_package_html_escape(label)}</span>"
        f"<strong>{_package_html_escape(counts.get(key, 0))}</strong>"
        "</div>"
        for key, label in (
            ("runs", "Runs"),
            ("findings", "Findings"),
            ("artifacts", "Artifacts"),
            ("targets", "Targets"),
        )
    )
    target_html = "".join(
        "<span class=\"chip\">"
        f"{_package_html_escape(target.get('type', 'target'))}: {_package_html_escape(target.get('value', ''))}"
        "</span>"
        for target in targets
        if isinstance(target, dict)
    ) or "<span class=\"muted\">No selected targets.</span>"
    project_notes = _entity_note_body(project)
    notes_html = (
        "<h2>Project Notes</h2>"
        f"<section class=\"card\"><p>{_package_html_escape(project_notes)}</p></section>"
        if project_notes else ""
    )

    run_html = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        run_id = str(run.get("id") or "")
        href = run_pages.get(run_id, "")
        text_href = run_text_paths.get(run_id, "")
        text_link = (
            f"<span>{_package_html_escape(run.get('output_line_count') or 0)} lines "
            f"· <a href=\"{_package_html_escape(text_href)}\">full text</a></span>"
            if text_href else
            f"<span>{_package_html_escape(run.get('output_line_count') or 0)} lines</span>"
        )
        run_html.append(
            "<li>"
            f"<a class=\"mono\" href=\"{_package_html_escape(href)}\">{_package_html_escape(run.get('command') or run_id)}</a>"
            "<div class=\"run-meta\">"
            f"<span>{_package_html_escape(run.get('started') or 'unknown start')}</span>"
            f"{text_link}"
            f"<span>{_package_html_escape(run.get('link_source') or 'manual')} link</span>"
            "</div>"
            "</li>"
        )
    if not run_html:
        run_html.append("<li class=\"muted\">No selected runs.</li>")

    finding_rows = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        finding_run_id = str(finding.get("run_id") or "")
        finding_href = _finding_run_anchor(finding) if finding_run_id in run_pages else ""
        finding_label = _package_html_escape(finding.get("title") or finding.get("raw_line"))
        finding_link = f"<a href=\"{finding_href}\">{finding_label}</a>" if finding_href else finding_label
        finding_title = _package_html_escape(finding.get("title") or finding.get("raw_line") or "")
        finding_severity = _package_html_escape(finding.get("severity") or "info")
        finding_status = _package_html_escape(finding.get("review_state") or "new")
        finding_run = _package_html_escape(_package_short_id(finding.get("run_id")))
        finding_rows.append(
            "<tr data-finding-row "
            f"data-finding=\"{finding_title}\" "
            f"data-severity=\"{finding_severity}\" "
            f"data-status=\"{finding_status}\" "
            f"data-run=\"{finding_run}\">"
            f"<td>{finding_link}</td>"
            f"<td>{finding_severity}</td>"
            f"<td>{finding_status}</td>"
            f"<td class=\"mono\">{finding_run}</td>"
            f"<td class=\"mono\">{_package_html_escape(finding.get('raw_line') or '')}"
            f"{_package_finding_metadata_html(finding)}</td>"
            "</tr>"
        )
    if not finding_rows:
        finding_rows.append("<tr><td colspan=\"5\" class=\"muted\">No selected findings.</td></tr>")

    artifact_rows = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        artifact_id = str(artifact.get("id") or "")
        href = artifact_paths.get(artifact_id, "")
        name = artifact.get("display_name") or artifact.get("workspace_path") or artifact_id
        link = (
            f"<a href=\"{_package_html_escape(href)}\">{_package_html_escape(name)}</a>"
            if href else _package_html_escape(name)
        )
        artifact_rows.append(
            "<tr>"
            f"<td>{link}</td>"
            f"<td>{_package_html_escape(artifact.get('workspace_path') or '')}</td>"
            f"<td>{_package_html_escape(artifact.get('byte_size') or 0)}</td>"
            f"<td class=\"mono\">{_package_html_escape(_package_short_id(artifact.get('run_id')))}</td>"
            "</tr>"
        )
    if not artifact_rows:
        artifact_rows.append("<tr><td colspan=\"4\" class=\"muted\">No selected artifacts.</td></tr>")

    skipped_html = ""
    if skipped_items:
        skipped_rows = "".join(
            "<li>"
            f"<span class=\"chip\">{_package_html_escape(item.get('kind') or 'item')}</span> "
            "<span class=\"mono\">"
            f"{_package_html_escape(item.get('label') or item.get('workspace_path') or item.get('id'))}"
            "</span>"
            f" <span class=\"muted\">{_package_html_escape(item.get('reason') or 'skipped')}</span>"
            "</li>"
            for item in skipped_items
        )
        skipped_html = f"<h2>Skipped Items</h2><section class=\"card\"><ul>{skipped_rows}</ul></section>"

    export_links = [
        ("Manifest JSON", "manifest.json"),
        ("README Markdown", "README.md"),
        ("Findings JSON", "findings/findings.json"),
        ("Findings Markdown", "findings/findings.md"),
        ("Targets JSON", "targets/targets.json"),
        ("Targets Markdown", "targets/targets.md"),
        ("Labels JSON", "metadata/labels.json"),
        ("Entity Notes JSON", "notes/entity-notes.json"),
        ("Entity Notes Markdown", "notes/entity-notes.md"),
    ]
    if project_notes:
        export_links.append(("Project Notes Markdown", "notes/project.md"))
    if skipped_items:
        export_links.append(("Skipped items JSON", "skipped-items.json"))
    export_html = "".join(
        "<li>"
        f"<a href=\"{_package_html_escape(href)}\">{_package_html_escape(label)}</a>"
        "</li>"
        for label, href in export_links
    )

    body = (
        "<main class=\"page\">"
        "<div class=\"topline\">darklab shell evidence package</div>"
        f"<h1>{_package_html_escape(package.get('name') or 'Evidence package')}</h1>"
        f"<p class=\"subtitle\">"
        f"{_package_html_escape(project.get('name') or 'Project')} · generated {_package_html_escape(generated_at)}"
        "</p>"
        f"<section class=\"grid\">{metric_html}</section>"
        f"{notes_html}"
        "<h2>Targets</h2>"
        f"<section class=\"card chips\">{target_html}</section>"
        "<h2>Runs</h2>"
        f"<ul class=\"run-list\">{''.join(run_html)}</ul>"
        "<h2>Findings</h2>"
        "<section class=\"card\">"
        "<table data-sort-table=\"findings\"><thead><tr>"
        "<th><button class=\"table-sort\" type=\"button\" data-sort-key=\"finding\">Finding</button></th>"
        "<th><button class=\"table-sort\" type=\"button\" data-sort-key=\"severity\">Severity</button></th>"
        "<th><button class=\"table-sort\" type=\"button\" data-sort-key=\"status\">Status</button></th>"
        "<th><button class=\"table-sort\" type=\"button\" data-sort-key=\"run\">Run</button></th>"
        "<th>Evidence</th></tr></thead>"
        f"<tbody>{''.join(finding_rows)}</tbody></table>"
        "</section>"
        "<h2>Artifacts</h2>"
        "<section class=\"card\">"
        "<table><thead><tr><th>Artifact</th><th>Workspace path</th><th>Bytes</th><th>Run</th></tr></thead>"
        f"<tbody>{''.join(artifact_rows)}</tbody></table>"
        "</section>"
        "<h2>Package Exports</h2>"
        f"<section class=\"card\"><ul>{export_html}</ul></section>"
        f"{skipped_html}"
        "<p class=\"footer\">Generated by darklab shell evidence packages. Redaction mode is recorded in manifest.json.</p>"
        "</main>"
    )
    return _package_page(
        str(package.get("name") or "Evidence package"),
        body,
        _package_index_sort_script(),
    )


def _render_package_readme(
    package,
    manifest,
    generated_at,
    run_pages,
    run_text_paths,
    artifact_paths,
    skipped_items,
):
    project = manifest.get("project") if isinstance(manifest.get("project"), dict) else {}
    counts = manifest.get("counts") if isinstance(manifest.get("counts"), dict) else {}
    targets = manifest.get("targets") if isinstance(manifest.get("targets"), list) else []
    runs = manifest.get("runs") if isinstance(manifest.get("runs"), list) else []
    findings = manifest.get("findings") if isinstance(manifest.get("findings"), list) else []
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), list) else []
    lines = [
        f"# {_package_markdown_text(package.get('name') or 'Evidence package')}",
        "",
        f"- Project: {_package_markdown_text(project.get('name') or 'Project')}",
        f"- Generated: {_package_markdown_text(generated_at)}",
        f"- Preset: {_package_markdown_text(manifest.get('preset') or 'custom')}",
        f"- Redaction mode: {_package_markdown_text(manifest.get('redaction_mode') or 'raw')}",
        "",
        "## Counts",
        "",
        "| Type | Count |",
        "| --- | ---: |",
    ]
    for key, label in (("runs", "Runs"), ("findings", "Findings"), ("artifacts", "Artifacts"), ("targets", "Targets")):
        lines.append(f"| {label} | {_package_int(counts.get(key))} |")
    project_notes = _entity_note_body(project)
    if project_notes:
        lines.extend([
            "",
            "## Project Notes",
            "",
            _package_markdown_text(project_notes),
        ])
    lines.extend(["", "## Targets", ""])
    if targets:
        for target in targets:
            if isinstance(target, dict):
                lines.append(
                    f"- {_package_markdown_code(target.get('type') or 'target')} "
                    f"{_package_markdown_text(target.get('value') or '')}"
                )
    else:
        lines.append("- No selected targets.")
    lines.extend(["", "## Runs", ""])
    if runs:
        for run in runs:
            if not isinstance(run, dict):
                continue
            run_id = str(run.get("id") or "")
            label = run.get("command") or run_id
            lines.append(f"- {_package_markdown_link(label, run_pages.get(run_id, ''))}")
            lines.append(f"  - Started: {_package_markdown_text(run.get('started') or 'unknown')}")
            lines.append(f"  - Lines: {_package_int(run.get('output_line_count'))}")
            if run_text_paths.get(run_id):
                lines.append(f"  - Full text: {_package_markdown_link('transcript text', run_text_paths[run_id])}")
    else:
        lines.append("- No selected runs.")
    lines.extend(["", "## Findings", ""])
    if findings:
        lines.extend(["| Finding | Severity | Status | Run | Evidence |", "| --- | --- | --- | --- | --- |"])
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            run_id = str(finding.get("run_id") or "")
            href = _finding_run_anchor(finding) if run_id in run_pages else ""
            finding_label = finding.get("title") or finding.get("raw_line") or finding.get("id")
            lines.append(
                f"| {_package_markdown_link(finding_label, href)} "
                f"| {_package_markdown_text(finding.get('severity') or 'info')} "
                f"| {_package_markdown_text(finding.get('review_state') or 'new')} "
                f"| {_package_markdown_code(_package_short_id(run_id))} "
                f"| {_package_markdown_code(finding.get('raw_line') or '')}"
                f"{_package_finding_metadata_markdown(finding)} |"
            )
    else:
        lines.append("- No selected findings.")
    lines.extend(["", "## Artifacts", ""])
    if artifacts:
        lines.extend(["| Artifact | Workspace Path | Bytes | Run |", "| --- | --- | ---: | --- |"])
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            artifact_id = str(artifact.get("id") or "")
            name = artifact.get("display_name") or artifact.get("workspace_path") or artifact_id
            lines.append(
                f"| {_package_markdown_link(name, artifact_paths.get(artifact_id, ''))} "
                f"| {_package_markdown_code(artifact.get('workspace_path') or '')} "
                f"| {_package_int(artifact.get('byte_size'))} "
                f"| {_package_markdown_code(_package_short_id(artifact.get('run_id')))} |"
            )
    else:
        lines.append("- No selected artifacts.")
    lines.extend(["", "## Skipped Items", ""])
    if skipped_items:
        for item in skipped_items:
            label = item.get("label") or item.get("workspace_path") or item.get("id") or "item"
            lines.append(
                f"- {_package_markdown_code(item.get('kind') or 'item')} "
                f"{_package_markdown_text(label)}: {_package_markdown_text(item.get('reason') or 'skipped')}"
            )
    else:
        lines.append("- No skipped items.")
    lines.extend([
        "",
        "## Package Exports",
        "",
        f"- {_package_markdown_link('Manifest JSON', 'manifest.json')}",
        f"- {_package_markdown_link('Findings JSON', 'findings/findings.json')}",
        f"- {_package_markdown_link('Findings Markdown', 'findings/findings.md')}",
        f"- {_package_markdown_link('Targets JSON', 'targets/targets.json')}",
        f"- {_package_markdown_link('Targets Markdown', 'targets/targets.md')}",
        f"- {_package_markdown_link('Labels JSON', 'metadata/labels.json')}",
        f"- {_package_markdown_link('Entity Notes JSON', 'notes/entity-notes.json')}",
        f"- {_package_markdown_link('Entity Notes Markdown', 'notes/entity-notes.md')}",
    ])
    if project_notes:
        lines.append(f"- {_package_markdown_link('Project Notes Markdown', 'notes/project.md')}")
    if skipped_items:
        lines.append(f"- {_package_markdown_link('Skipped items JSON', 'skipped-items.json')}")
    lines.extend([
        "",
        "## Notes",
        "",
        "Generated by darklab shell evidence packages. Redaction mode is recorded in manifest.json.",
        "",
    ])
    return "\n".join(lines)


def _package_collection_json_bytes(collection_name, items, generated_at, *, extra=None):
    exported = items if isinstance(items, list) else []
    payload = {
        "format": 1,
        "generated_at": generated_at,
        "count": len(exported),
        collection_name: exported,
    }
    if extra:
        payload.update(extra)
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _package_collection_markdown_bytes(title, generated_at, body_lines, *, empty_message):
    lines = [f"# {_package_markdown_text(title)}", ""]
    if generated_at is not None:
        lines.extend([f"Generated: {_package_markdown_text(generated_at)}", ""])
    body = [str(line) for line in body_lines] if isinstance(body_lines, list) else []
    if body:
        lines.extend(body)
    else:
        lines.extend([empty_message, ""])
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def _package_findings_json_bytes(manifest, generated_at, run_pages):
    findings = manifest.get("findings") if isinstance(manifest.get("findings"), list) else []
    exported = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        item = dict(finding)
        run_id = str(item.get("run_id") or "")
        if run_id in run_pages:
            item["run_page"] = _finding_run_anchor(item)
        exported.append(item)
    return _package_collection_json_bytes("findings", exported, generated_at)


def _package_findings_markdown_bytes(manifest, run_pages):
    findings = manifest.get("findings") if isinstance(manifest.get("findings"), list) else []
    finding_count = len([item for item in findings if isinstance(item, dict)])
    lines = [
        "# Findings",
        "",
        f"Selected findings: {finding_count}",
        "",
    ]
    if findings:
        lines.extend(["| Finding | Severity | Status | Run | Evidence |", "| --- | --- | --- | --- | --- |"])
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            run_id = str(finding.get("run_id") or "")
            href = f"../{_finding_run_anchor(finding)}" if run_id in run_pages else ""
            finding_label = finding.get("title") or finding.get("raw_line") or finding.get("id")
            lines.append(
                f"| {_package_markdown_link(finding_label, href)} "
                f"| {_package_markdown_text(finding.get('severity') or 'info')} "
                f"| {_package_markdown_text(finding.get('review_state') or 'new')} "
                f"| {_package_markdown_code(_package_short_id(run_id))} "
                f"| {_package_markdown_code(finding.get('raw_line') or '')}"
                f"{_package_finding_metadata_markdown(finding)} |"
            )
        lines.extend(["", "## Finding Details", ""])
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            finding_label = _package_markdown_text(
                finding.get("title") or finding.get("raw_line") or finding.get("id") or "Finding"
            )
            source_line = finding.get("line_number") if finding.get("line_number") is not None else ""
            lines.extend([
                f"### {finding_label}",
                "",
                f"- ID: {_package_markdown_code(finding.get('id') or '')}",
                f"- Run: {_package_markdown_code(finding.get('run_id') or '')}",
                f"- Scope: {_package_markdown_code(finding.get('scope') or 'finding')}",
                f"- Severity: {_package_markdown_code(finding.get('severity') or 'info')}",
                f"- Review state: {_package_markdown_code(finding.get('review_state') or 'new')}",
                f"- Source line: {_package_markdown_code(source_line)}",
            ])
            target_ids = _package_finding_target_ids(finding)
            if target_ids:
                lines.append("- Targets: " + ", ".join(_package_markdown_code(target_id) for target_id in target_ids))
            raw_line = str(finding.get("raw_line") or "").replace("\r\n", "\n").replace("\r", "\n").strip()
            if raw_line:
                lines.extend(["", "```text", raw_line.replace("```", "`\u200b``"), "```"])
            metadata = _package_finding_metadata_markdown(finding).replace("<br>", "\n")
            if metadata.strip():
                lines.extend(["", metadata.strip()])
            lines.append("")
    else:
        lines.append("- No selected findings.")
    return _package_collection_markdown_bytes(
        "Findings",
        None,
        lines[2:],
        empty_message="- No selected findings.",
    )


def _package_finding_target_ids(finding):
    target_ids = []
    primary = str(finding.get("target_id") or "") if isinstance(finding, dict) else ""
    if primary:
        target_ids.append(primary)
    raw_target_ids = finding.get("target_ids") if isinstance(finding, dict) else None
    if isinstance(raw_target_ids, list):
        for target_id in raw_target_ids:
            normalized = str(target_id or "")
            if normalized and normalized not in target_ids:
                target_ids.append(normalized)
    return target_ids


def _package_targets_json_bytes(manifest, generated_at):
    targets = manifest.get("targets") if isinstance(manifest.get("targets"), list) else []
    findings = manifest.get("findings") if isinstance(manifest.get("findings"), list) else []
    exported = []
    for target in targets:
        if not isinstance(target, dict):
            continue
        item = dict(target)
        target_id = str(item.get("id") or "")
        finding_refs = []
        run_refs = []
        if target_id:
            for finding in findings:
                if not isinstance(finding, dict) or target_id not in _package_finding_target_ids(finding):
                    continue
                finding_id = str(finding.get("id") or "")
                run_id = str(finding.get("run_id") or "")
                if finding_id and finding_id not in finding_refs:
                    finding_refs.append(finding_id)
                if run_id and run_id not in run_refs:
                    run_refs.append(run_id)
        source_run_id = str(item.get("source_run_id") or "")
        if source_run_id and source_run_id not in run_refs:
            run_refs.append(source_run_id)
        item["finding_ids"] = finding_refs
        item["run_ids"] = run_refs
        exported.append(item)
    return _package_collection_json_bytes("targets", exported, generated_at)


def _package_targets_markdown_bytes(manifest):
    targets = manifest.get("targets") if isinstance(manifest.get("targets"), list) else []
    findings = manifest.get("findings") if isinstance(manifest.get("findings"), list) else []
    lines = ["# Targets", "", f"Selected targets: {len([item for item in targets if isinstance(item, dict)])}", ""]
    if not targets:
        lines.append("- No selected targets.")
        return _package_collection_markdown_bytes(
            "Targets",
            None,
            lines[2:],
            empty_message="- No selected targets.",
        )
    for target in targets:
        if not isinstance(target, dict):
            continue
        target_id = str(target.get("id") or "")
        raw_labels = target.get("labels")
        labels = raw_labels if isinstance(raw_labels, list) else []
        primary_label = ""
        for label in labels:
            if isinstance(label, dict) and label.get("label"):
                primary_label = str(label.get("label") or "")
                break
        target_label = _package_markdown_text(primary_label or target.get("value") or target_id or "Target")
        lines.extend([
            f"## {target_label}",
            "",
            f"- ID: {_package_markdown_code(target_id)}",
            f"- Type: {_package_markdown_code(target.get('type') or 'target')}",
            f"- Value: {_package_markdown_code(target.get('value') or '')}",
        ])
        note = target.get("note") if isinstance(target.get("note"), dict) else None
        if note and note.get("body"):
            lines.extend(["", "### Notes", "", _package_markdown_text(note.get("body") or "")])
        if labels:
            label_values = [
                _package_markdown_code(label.get("label") or "")
                for label in labels
                if isinstance(label, dict) and label.get("label")
            ]
            if label_values:
                lines.extend(["", "### Labels", "", ", ".join(label_values)])
        note = target.get("note") if isinstance(target.get("note"), dict) else None
        if note and note.get("body"):
            lines.extend(["", "### Entity Note", "", _package_markdown_text(note.get("body") or "")])
        linked_findings = [
            finding for finding in findings
            if isinstance(finding, dict) and target_id in _package_finding_target_ids(finding)
        ]
        if linked_findings:
            lines.extend(["", "### Related Findings", ""])
            for finding in linked_findings:
                finding_label = _package_markdown_text(finding.get("title") or finding.get("raw_line") or finding.get("id"))
                lines.append(f"- {finding_label} ({_package_markdown_code(finding.get('id') or '')})")
        lines.append("")
    return _package_collection_markdown_bytes(
        "Targets",
        None,
        lines[2:],
        empty_message="- No selected targets.",
    )


def _package_metadata_targets(package, manifest):
    targets = {
        "project": [str(package.get("project_id") or "")],
        "package": [str(package.get("id") or "")],
    }
    selected = manifest.get("selected_entity_ids") if isinstance(manifest.get("selected_entity_ids"), dict) else {}
    mapping = {
        "run": "run_ids",
        "finding": "finding_ids",
        "run_file_artifact": "artifact_ids",
        "target": "target_ids",
    }
    for entity_type, key in mapping.items():
        raw_ids = selected.get(key)
        if isinstance(raw_ids, list):
            targets[entity_type] = [str(value or "") for value in raw_ids if str(value or "")]
    return {
        entity_type: sorted({entity_id for entity_id in entity_ids if entity_id})
        for entity_type, entity_ids in targets.items()
        if any(entity_ids)
    }


def _metadata_items_by_entity(items):
    by_entity = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        key = (str(item.get("entity_type") or ""), str(item.get("entity_id") or ""))
        if not key[0] or not key[1]:
            continue
        by_entity.setdefault(key, []).append(item)
    return by_entity


def _package_manifest_with_inline_metadata(manifest, labels, notes):
    enriched = dict(manifest)
    label_map = _metadata_items_by_entity(labels)
    note_map = _metadata_items_by_entity(notes)

    def _enrich_items(entity_type, key):
        source_items = manifest.get(key) if isinstance(manifest.get(key), list) else []
        enriched_items = []
        for source_item in source_items:
            if not isinstance(source_item, dict):
                continue
            item = dict(source_item)
            entity_id = str(item.get("id") or "")
            item_labels = label_map.get((entity_type, entity_id), [])
            item_note = note_map.get((entity_type, entity_id), [])
            if item_labels:
                item["labels"] = item_labels
            if item_note:
                item["note"] = item_note[0]
            enriched_items.append(item)
        enriched[key] = enriched_items

    _enrich_items("run", "runs")
    _enrich_items("finding", "findings")
    _enrich_items("run_file_artifact", "artifacts")
    _enrich_items("target", "targets")
    project = manifest.get("project") if isinstance(manifest.get("project"), dict) else {}
    enriched_project = dict(project)
    project_id = str(project.get("id") or "")
    project_labels = label_map.get(("project", project_id), [])
    project_note = note_map.get(("project", project_id), [])
    if project_labels:
        enriched_project["labels"] = project_labels
    if project_note:
        enriched_project["note"] = project_note[0]
    enriched["project"] = enriched_project
    return enriched


def _package_metadata_rows(conn, session_id, table, targets):
    rows = []
    for entity_type, entity_ids in targets.items():
        if not entity_ids:
            continue
        placeholders = ",".join("?" for _ in entity_ids)
        if table == "entity_labels":
            rows.extend(conn.execute(
                "SELECT id, entity_type, entity_id, label, source, created "  # nosec
                f"FROM entity_labels WHERE session_id = ? AND entity_type = ? "
                f"AND entity_id IN ({placeholders}) ORDER BY entity_type ASC, entity_id ASC, label ASC",
                [session_id, entity_type, *entity_ids],
            ).fetchall())
        elif table == "entity_notes":
            rows.extend(conn.execute(
                "SELECT id, entity_type, entity_id, body, created, updated "  # nosec
                f"FROM entity_notes WHERE session_id = ? AND entity_type = ? "
                f"AND entity_id IN ({placeholders}) ORDER BY entity_type ASC, entity_id ASC, updated ASC, id ASC",
                [session_id, entity_type, *entity_ids],
            ).fetchall())
    return rows


def _package_label_dicts(labels, redaction_rules=None):
    return [
        _redact_package_value({
            "id": row["id"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "label": row["label"],
            "source": row["source"],
            "created": row["created"],
        }, redaction_rules)
        for row in labels
    ]


def _package_labels_json_bytes(labels, generated_at, redaction_rules=None):
    exported = _package_label_dicts(labels, redaction_rules)
    return _package_collection_json_bytes("labels", exported, generated_at)


def _package_note_dicts(notes, redaction_rules=None):
    return [
        _redact_package_value({
            "id": row["id"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "body": row["body"],
            "created": row["created"],
            "updated": row["updated"],
        }, redaction_rules)
        for row in notes
    ]


def _package_notes_json_bytes(notes, generated_at, *, included, redaction_rules=None):
    exported = _package_note_dicts(notes, redaction_rules)
    return _package_collection_json_bytes(
        "notes",
        exported,
        generated_at,
        extra={"include_private_notes": bool(included)},
    )


def _package_project_notes_markdown_bytes(manifest, generated_at):
    project = manifest.get("project") if isinstance(manifest.get("project"), dict) else {}
    project_notes = _package_markdown_text(_entity_note_body(project))
    lines = []
    if project_notes:
        lines.extend([project_notes, ""])
    else:
        lines.extend(["No project notes were included in this package.", ""])
    return _package_collection_markdown_bytes(
        f"{project.get('name') or 'Project'} Notes",
        generated_at,
        lines,
        empty_message="No project notes were included in this package.",
    )


def _package_notes_markdown_bytes(notes, generated_at, *, included):
    lines = []
    if not included:
        return _package_collection_markdown_bytes(
            "Entity Notes",
            generated_at,
            ["Private entity notes were excluded from this package.", ""],
            empty_message="Private entity notes were excluded from this package.",
        )
    if not notes:
        return _package_collection_markdown_bytes(
            "Entity Notes",
            generated_at,
            ["No selected entity notes were included in this package.", ""],
            empty_message="No selected entity notes were included in this package.",
        )

    for note in notes:
        if not isinstance(note, dict):
            continue
        entity_type = _package_markdown_text(note.get("entity_type") or "entity")
        entity_id = _package_markdown_code(_package_short_id(note.get("entity_id")))
        updated = _package_markdown_text(note.get("updated") or note.get("created") or "unknown")
        body = _package_markdown_text(note.get("body") or "")
        lines.extend([
            f"## {entity_type} {entity_id}",
            "",
            f"- Updated: {updated}",
            "",
            body or "_No note body._",
            "",
        ])
    return _package_collection_markdown_bytes(
        "Entity Notes",
        generated_at,
        lines,
        empty_message="No selected entity notes were included in this package.",
    )
