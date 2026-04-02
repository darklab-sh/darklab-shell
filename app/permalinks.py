"""
Permalink page rendering — styled HTML pages for run history and tab snapshots.
"""

import json

from flask import Response

from config import CFG


def _format_retention(days: int) -> str:
    """Return a human-friendly retention description for use in error messages."""
    if days == 0:
        return "unlimited — snapshots are never automatically deleted"
    if days % 365 == 0:
        n = days // 365
        return f"{n} year{'s' if n != 1 else ''}"
    if days % 30 == 0:
        n = days // 30
        return f"{n} month{'s' if n != 1 else ''}"
    return f"{days} day{'s' if days != 1 else ''}"


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
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{app_name} — {noun} not found</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;700&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #0d0d0d; --surface: #141414; --border: #2e2e2e;
    --green: #39ff14; --green-dim: #1a7a08; --green-glow: rgba(57,255,20,0.12);
    --amber: #ffb800; --muted: #606060; --text: #e0e0e0;
    --font: 'JetBrains Mono', monospace;
  }}
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: var(--font);
          font-size: 13px; display: flex; flex-direction: column; min-height: 100vh; }}
  header {{ display: flex; align-items: center; gap: 16px; padding: 14px 20px;
            border-bottom: 1px solid var(--border); background: #111; flex-wrap: wrap; }}
  header h1 {{ font-size: 14px; font-weight: 300; letter-spacing: 3px; color: var(--green);
               text-shadow: 0 0 16px var(--green-glow); }}
  .actions {{ margin-left: auto; display: flex; gap: 8px; }}
  .btn {{ background: transparent; border: 1px solid var(--border); color: var(--muted);
          font-family: var(--font); font-size: 11px; padding: 4px 12px; border-radius: 3px;
          cursor: pointer; text-decoration: none; transition: border-color .2s, color .2s; }}
  .btn:hover {{ border-color: var(--green-dim); color: var(--green); }}
  #output {{ flex: 1; padding: 20px; line-height: 1.65; }}
  .error-heading {{ color: var(--amber); font-weight: 700; margin-bottom: 12px; }}
  .error-detail {{ color: var(--muted); }}
</style>
</head>
<body>
<header>
  <h1>{app_name}</h1>
  <div class="actions">
    <a class="btn" href="/">← back to shell</a>
  </div>
</header>
<div id="output">
  <div class="error-heading">{noun} not found</div>
  <div class="error-detail">{detail}</div>
</div>
</body>
</html>"""
    return Response(html, status=404, mimetype="text/html")


def _permalink_page(title, label, created, content_lines, json_url) -> Response:
    """Render a self-contained HTML page for a permalink.
    content_lines can be a list of strings (single-run history) or
    a list of {text, cls} objects (tab snapshots with class info)."""
    app_name   = CFG.get("app_name", "shell.darklab.sh")
    lines_json = json.dumps(content_lines)
    label_json = json.dumps(label)
    created_fmt = created[:19].replace("T", " ") + " UTC"
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{app_name} — {title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;700&display=swap" rel="stylesheet">
<script src="/static/js/vendor/ansi_up.js"></script>
<style>
  :root {{
    --bg: #0d0d0d; --surface: #141414; --border: #2e2e2e;
    --green: #39ff14; --green-dim: #1a7a08; --green-glow: rgba(57,255,20,0.12);
    --amber: #ffb800; --red: #ff3c3c; --muted: #606060; --text: #e0e0e0;
    --font: 'JetBrains Mono', monospace;
  }}
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: var(--font);
          font-size: 13px; display: flex; flex-direction: column; min-height: 100vh; }}
  header {{ display: flex; align-items: center; gap: 16px; padding: 14px 20px;
            border-bottom: 1px solid var(--border); background: #111; flex-wrap: wrap; }}
  header h1 {{ font-size: 14px; font-weight: 300; letter-spacing: 3px; color: var(--green);
               text-shadow: 0 0 16px var(--green-glow); }}
  .meta {{ font-size: 11px; color: var(--muted); }}
  .actions {{ margin-left: auto; display: flex; gap: 8px; flex-wrap: wrap; }}
  .btn {{ background: transparent; border: 1px solid var(--border); color: var(--muted);
          font-family: var(--font); font-size: 11px; padding: 4px 12px; border-radius: 3px;
          cursor: pointer; text-decoration: none; transition: border-color .2s, color .2s; }}
  .btn:hover {{ border-color: var(--green-dim); color: var(--green); }}
  #output {{ flex: 1; padding: 20px; line-height: 1.65; white-space: pre-wrap;
             word-break: break-all; overflow-y: auto; }}
  .line {{ display: block; }}
  .line.exit-ok   {{ color: var(--green); font-weight: 700; margin-top: 8px; }}
  .line.exit-fail {{ color: var(--red);   font-weight: 700; margin-top: 8px; }}
  .line.notice    {{ color: #6ab0f5; font-style: italic; }}
  .line.denied    {{ color: var(--amber); font-weight: 700; }}
  a {{ color: var(--green); }}
</style>
</head>
<body>
<header>
  <h1>{app_name}</h1>
  <div class="meta">{created_fmt}</div>
  <div class="actions">
    <a class="btn" href="{json_url}">view json</a>
    <button class="btn" onclick="saveTxt()">save .txt</button>
    <a class="btn" href="/">← back to shell</a>
  </div>
</header>
<div id="output"></div>
<script>
  const lines = {lines_json};
  const ansi_up = new AnsiUp();
  ansi_up.use_classes = false;
  const out = document.getElementById('output');
  const plainClasses = new Set(['exit-ok', 'exit-fail', 'denied', 'notice']);

  // Show the command as the first line
  const cmdSpan = document.createElement('span');
  cmdSpan.className = 'line';
  cmdSpan.style.color = 'var(--green)';
  cmdSpan.style.marginBottom = '4px';
  cmdSpan.style.display = 'block';
  cmdSpan.textContent = '$ ' + {label_json};
  out.appendChild(cmdSpan);
  const gapSpan = document.createElement('span');
  gapSpan.className = 'line';
  gapSpan.textContent = '';
  out.appendChild(gapSpan);

  lines.forEach(entry => {{
    const span = document.createElement('span');
    // Support both plain strings (single-run history) and {{text, cls}} objects (snapshots)
    const text = typeof entry === 'string' ? entry : entry.text;
    const cls  = typeof entry === 'string' ? '' : (entry.cls || '');
    span.className = 'line' + (cls ? ' ' + cls : '');
    if (plainClasses.has(cls)) {{
      span.textContent = text;
    }} else {{
      span.innerHTML = ansi_up.ansi_to_html(text);
    }}
    out.appendChild(span);
  }});

  function saveTxt() {{
    const text = lines.map(e => typeof e === 'string' ? e : e.text).join('\\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], {{type: 'text/plain'}}));
    a.download = 'shell.darklab.sh-export.txt';
    a.click();
    URL.revokeObjectURL(a.href);
  }}
</script>
</body>
</html>"""
    return Response(html, mimetype="text/html")
