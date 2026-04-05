"""
Permalink page rendering — styled HTML pages for run history and tab snapshots.
"""

import json
from datetime import datetime, timedelta, timezone

from flask import Response

from config import CFG


def _format_retention(days: int) -> str:
    """Return a human-friendly retention description for use in error messages.
    Decomposes any number of days into years (365), months (30), and remainder days,
    joining non-zero parts with commas and 'and', e.g. '1 year, 2 months and 5 days'."""
    if days == 0:
        return "unlimited — snapshots are never automatically deleted"

    def _unit(n: int, singular: str) -> str:
        return f"{n} {singular}{'s' if n != 1 else ''}"

    years,   r     = divmod(days, 365)
    months,  rem   = divmod(r,    30)
    parts = []
    if years:
        parts.append(_unit(years, "year"))
    if months:
        parts.append(_unit(months, "month"))
    if rem:
        parts.append(_unit(rem, "day"))
    if not parts:
        parts = [_unit(days, "day")]  # days=0 already returned above; unreachable

    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


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


def _expiry_note(created: str) -> str:
    """Return an HTML snippet showing how long until this permalink expires,
    or an empty string if retention is unlimited or the date can't be parsed."""
    retention = CFG.get("permalink_retention_days", 0)
    if not retention:
        return ""
    try:
        created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        if created_dt.tzinfo is None:
            created_dt = created_dt.replace(tzinfo=timezone.utc)
        expiry_dt  = created_dt + timedelta(days=retention)
        remaining  = expiry_dt - datetime.now(timezone.utc)
        days_left  = remaining.days  # integer floor; 0 means < 24 h remaining
        if remaining.total_seconds() <= 0:
            return ""  # already pruned / about to be; 404 page would have shown instead
        expiry_date = expiry_dt.strftime("%Y-%m-%d")
        if days_left == 0:
            label = "expires today"
        else:
            label = f"expires in {_format_retention(days_left)}"
        return (
            f'<div class="meta expiry" title="Expires {expiry_date}">'
            f'{label} &nbsp;·&nbsp; {expiry_date}'
            f'</div>'
        )
    except Exception:
        return ""


def _permalink_page(title, label, created, content_lines, json_url, extra_actions=None) -> Response:
    """Render a self-contained HTML page for a permalink.
    content_lines can be a list of strings (single-run history) or
    a list of {text, cls} objects (tab snapshots with class info)."""
    app_name   = CFG.get("app_name", "shell.darklab.sh")
    lines_json = json.dumps(content_lines)
    label_json = json.dumps(label)
    created_fmt = created[:19].replace("T", " ") + " UTC"
    expiry_html = _expiry_note(created)
    extra_actions = extra_actions or []
    extra_action_html = "".join(
        f'<a class="btn" href="{action["href"]}">{action["label"]}</a>'
        for action in extra_actions
    )
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
  .meta.expiry {{ color: var(--amber); }}
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
  {expiry_html}
  <div class="actions">
    {extra_action_html}
    <a class="btn" href="{json_url}">view json</a>
    <button class="btn" onclick="copyTxt()">copy</button>
    <button class="btn" onclick="saveTxt()">save .txt</button>
    <button class="btn" onclick="saveHtml()">save .html</button>
    <a class="btn" href="/">← back to shell</a>
  </div>
</header>
<div id="output"></div>
<div id="copy-toast" style="position:fixed;bottom:24px;left:50%;transform:translateX(-50%) translateY(60px);
background:#1a1a1a;border:1px solid #1a7a08;color:#39ff14;font-family:'JetBrains Mono',monospace;
font-size:12px;padding:10px 18px;border-radius:4px;z-index:300;
transition:transform 0.3s ease;pointer-events:none;">Copied to clipboard</div>
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

  function _showToast() {{
    const t = document.getElementById('copy-toast');
    t.style.transform = 'translateX(-50%) translateY(0)';
    setTimeout(() => {{ t.style.transform = 'translateX(-50%) translateY(60px)'; }}, 2500);
  }}

  function copyTxt() {{
    const text = lines.map(e => typeof e === 'string' ? e : e.text).join('\\n');
    navigator.clipboard.writeText(text).then(_showToast);
  }}

  function saveTxt() {{
    const text = lines.map(e => typeof e === 'string' ? e : e.text).join('\\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], {{type: 'text/plain'}}));
    a.download = 'shell.darklab.sh-export.txt';
    a.click();
    URL.revokeObjectURL(a.href);
  }}

  function escHtml(t) {{
    return t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }}

  function saveHtml() {{
    const plainClsSet = new Set(['exit-ok', 'exit-fail', 'denied', 'notice']);
    const appName = {json.dumps(app_name)};
    const label   = {label_json};
    const created = {json.dumps(created_fmt)};

    const linesHtml = lines.map(entry => {{
      const text = typeof entry === 'string' ? entry : entry.text;
      const cls  = typeof entry === 'string' ? '' : (entry.cls || '');
      const tsC  = (entry && entry.tsC) ? entry.tsC : '';
      const tsSpan = tsC ? '<span class="ts">' + escHtml(tsC) + '</span>' : '';
      const content = plainClsSet.has(cls)
        ? escHtml(text)
        : ansi_up.ansi_to_html(text);
      return '<span class="line' + (cls ? ' ' + cls : '') + '">' + tsSpan + content + '</span>';
    }}).join('\\n');

    const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>${{escHtml(label)}} \u2014 ${{escHtml(appName)}}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
  body {{
    background: #0d0d0d; color: #e0e0e0;
    font-family: 'JetBrains Mono', monospace; font-size: 13px;
    padding: 28px 32px; margin: 0; line-height: 1.65;
  }}
  .header {{
    margin-bottom: 20px; padding-bottom: 14px;
    border-bottom: 1px solid #1f1f1f;
  }}
  .app-name {{ color: #39ff14; font-size: 18px; letter-spacing: 3px; margin-bottom: 6px; }}
  .meta {{ color: #606060; font-size: 11px; }}
  .output {{ white-space: pre-wrap; word-break: break-all; }}
  .line {{ display: block; }}
  .line.exit-ok   {{ color: #39ff14; font-weight: 700; margin-top: 8px; }}
  .line.exit-fail {{ color: #ff3c3c; font-weight: 700; margin-top: 8px; }}
  .line.denied    {{ color: #ffb800; font-weight: 700; }}
  .line.notice    {{ color: #6ab0f5; font-style: italic; }}
  .ts {{
    display: inline-block; min-width: 58px; text-align: right;
    color: #505050; font-size: 10px; user-select: none;
    padding-right: 8px; margin-right: 6px;
    border-right: 1px solid #1f1f1f;
    font-variant-numeric: tabular-nums;
  }}
</style>
</head>
<body>
<div class="header">
  <div class="app-name">${{escHtml(appName)}}</div>
  <div class="meta">${{escHtml(label)}} &nbsp;&middot;&nbsp; ${{escHtml(created)}}</div>
</div>
<div class="output">
${{linesHtml}}
</div>
</body>
</html>`;

    const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([html], {{type: 'text/html'}}));
    a.download = appName + '-' + ts + '.html';
    a.click();
    URL.revokeObjectURL(a.href);
  }}
</script>
</body>
</html>"""
    return Response(html, mimetype="text/html")
