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
    is_structured_snapshot = any(
        entry and isinstance(entry, dict)
        for entry in content_lines
    )
    normalized_lines = []
    if is_structured_snapshot:
        has_prompt_echo = any(
            isinstance(entry, dict) and str(entry.get("cls", "")) == "prompt-echo"
            for entry in content_lines
        )
        if not has_prompt_echo:
            normalized_lines.append({"text": f"$ {label}", "cls": "prompt-echo", "tsC": "", "tsE": ""})
            normalized_lines.append({"text": "", "cls": "", "tsC": "", "tsE": ""})
        for entry in content_lines:
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
        for entry in content_lines:
            normalized_lines.append({"text": str(entry), "cls": "", "tsC": "", "tsE": ""})
    has_timestamp_metadata = any(line.get("tsC") or line.get("tsE") for line in normalized_lines)
    lines_json = json.dumps(normalized_lines)
    label_json = json.dumps(label)
    created_fmt = created[:19].replace("T", " ") + " UTC"
    expiry_html = _expiry_note(created)
    extra_actions = extra_actions or []
    toggle_ts_attrs = (
        ' disabled title="timestamps unavailable for this permalink"'
        if not has_timestamp_metadata else ""
    )
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
  .btn:disabled {{ opacity: 0.35; cursor: not-allowed; }}
  #output {{ flex: 1; padding: 20px; line-height: 1.65; white-space: pre-wrap;
             word-break: break-all; overflow-y: auto; }}
  .line {{ display: block; }}
  .line.exit-ok   {{ color: var(--green); font-weight: 700; margin-top: 8px; }}
  .line.exit-fail {{ color: var(--red);   font-weight: 700; margin-top: 8px; }}
  .line.notice    {{ color: #6ab0f5; font-style: italic; }}
  .line.denied    {{ color: var(--amber); font-weight: 700; }}
  .perm-prefix {{ display: inline-block; min-width: var(--perm-prefix-width, 0ch); margin-right: 14px;
                  color: #6a6a6a; font-size: 11px; text-align: right; user-select: none;
                  font-variant-numeric: tabular-nums; }}
  .perm-content {{ display: inline; }}
  .prompt-prefix {{ color: #6ab0f5; font-weight: 700; margin-right: 8px; }}
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
    <button class="btn" id="toggle-ln">line numbers: off</button>
    <button class="btn" id="toggle-ts"{toggle_ts_attrs}>timestamps: off</button>
    <a class="btn" href="{json_url}">view json</a>
    <button class="btn" onclick="copyTxt()">copy</button>
    <button class="btn" onclick="saveTxt()">save .txt</button>
    <button class="btn" onclick="saveHtml()">save .html</button>
    <a class="btn" href="/">← back to shell</a>
  </div>
</header>
<div id="output"></div>
<div id="copy-toast" style="display:none;position:fixed;bottom:24px;left:50%;transform:translateX(-50%) translateY(60px);
background:#1a1a1a;border:1px solid #1a7a08;color:#39ff14;font-family:'JetBrains Mono',monospace;
font-size:12px;padding:10px 18px;border-radius:4px;z-index:300;
transition:transform 0.3s ease;
pointer-events:none;">Copied to clipboard</div>
<style>
  #copy-toast.show {{
    transform: translateX(-50%) translateY(0);
  }}
  @media (max-width: 768px) {{
    #copy-toast {{
      bottom: calc(112px + env(safe-area-inset-bottom)) !important;
      max-width: calc(100vw - 24px);
      text-align: center;
    }}
  }}
</style>
<script>
  const lines = {lines_json};
  const hasTimestampMetadata = {json.dumps(has_timestamp_metadata)};
  const ansi_up = new AnsiUp();
  ansi_up.use_classes = false;
  const out = document.getElementById('output');
  const plainClasses = new Set(['exit-ok', 'exit-fail', 'denied', 'notice']);
  const tsModes = ['off', 'elapsed', 'clock'];
  function getCookie(name) {{
    const prefix = `${{name}}=`;
    const match = document.cookie.split(';').map(part => part.trim()).find(part => part.startsWith(prefix));
    return match ? decodeURIComponent(match.slice(prefix.length)) : '';
  }}
  const prefLineNumbers = getCookie('pref_line_numbers');
  const prefTimestamps = getCookie('pref_timestamps');
  let lnMode = prefLineNumbers === 'on' ? 'on' : 'off';
  let tsMode = tsModes.includes(prefTimestamps) ? prefTimestamps : 'off';
  if (!hasTimestampMetadata) tsMode = 'off';

  function renderPromptEcho(text) {{
    const raw = String(text || '');
    const firstSpace = raw.indexOf(' ');
    const prefix = firstSpace === -1 ? raw : raw.slice(0, firstSpace);
    const remainder = firstSpace === -1 ? '' : raw.slice(firstSpace + 1);
    return '<span class="prompt-prefix">' + escHtml(prefix) + '</span>'
      + (remainder ? escHtml(' ' + remainder) : '');
  }}

  function timestampText(entry) {{
    if (tsMode === 'clock') return entry.tsC || '';
    if (tsMode === 'elapsed') return entry.tsE || '';
    return '';
  }}

  function formatPrefix(index, entry) {{
    const parts = [];
    if (lnMode === 'on') parts.push(String(index));
    const ts = timestampText(entry);
    if (ts) parts.push(ts);
    return parts.join(' ');
  }}

  function displayText(entry, index) {{
    const prefix = formatPrefix(index + 1, entry);
    return (prefix ? prefix + '  ' : '') + String(entry.text || '');
  }}

  function renderOutput() {{
    out.innerHTML = '';
    const prefixes = lines.map((entry, index) => formatPrefix(index + 1, entry));
    const prefixWidth = Math.max(0, ...prefixes.map(prefix => prefix.length));
    out.style.setProperty('--perm-prefix-width', `${{prefixWidth}}ch`);

    lines.forEach((entry, index) => {{
      const span = document.createElement('span');
      const cls = entry.cls || '';
      span.className = 'line' + (cls ? ' ' + cls : '');

      const prefix = formatPrefix(index + 1, entry);
      if (prefix) {{
        const prefixEl = document.createElement('span');
        prefixEl.className = 'perm-prefix';
        prefixEl.textContent = prefix;
        span.appendChild(prefixEl);
      }}

      const contentEl = document.createElement('span');
      contentEl.className = 'perm-content';
      if (cls === 'prompt-echo') {{
        contentEl.innerHTML = renderPromptEcho(entry.text);
      }} else if (plainClasses.has(cls)) {{
        contentEl.textContent = entry.text;
      }} else {{
        contentEl.innerHTML = ansi_up.ansi_to_html(entry.text);
      }}
      span.appendChild(contentEl);
      out.appendChild(span);
    }});

    document.getElementById('toggle-ln').textContent = `line numbers: ${{lnMode}}`;
    const tsBtn = document.getElementById('toggle-ts');
    tsBtn.textContent = hasTimestampMetadata ? `timestamps: ${{tsMode}}` : 'timestamps: unavailable';
  }}

  document.getElementById('toggle-ln').addEventListener('click', () => {{
    lnMode = lnMode === 'on' ? 'off' : 'on';
    renderOutput();
  }});

  document.getElementById('toggle-ts').addEventListener('click', () => {{
    if (!hasTimestampMetadata) return;
    tsMode = tsModes[(tsModes.indexOf(tsMode) + 1) % tsModes.length];
    renderOutput();
  }});

  renderOutput();

  function _showToast() {{
    const t = document.getElementById('copy-toast');
    t.style.display = 'block';
    t.offsetHeight;
    t.classList.add('show');
    setTimeout(() => {{
      t.classList.remove('show');
      t.style.display = 'none';
    }}, 2500);
  }}

  function _copyTextFallback(text) {{
    return new Promise((resolve, reject) => {{
      const textarea = document.createElement('textarea');
      textarea.value = String(text);
      textarea.setAttribute('readonly', '');
      textarea.style.position = 'fixed';
      textarea.style.top = '-9999px';
      textarea.style.left = '-9999px';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      textarea.setSelectionRange(0, textarea.value.length);
      let copied = false;
      try {{
        copied = typeof document.execCommand === 'function' && document.execCommand('copy');
      }} catch (_) {{
        copied = false;
      }}
      textarea.remove();
      if (copied) resolve(true);
      else reject(new Error('Copy command failed'));
    }});
  }}

  function _copyTextToClipboard(text) {{
    const value = String(text || '');
    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {{
      return navigator.clipboard.writeText(value).catch(() => _copyTextFallback(value));
    }}
    return _copyTextFallback(value);
  }}

  function copyTxt() {{
    const text = lines.map((entry, index) => displayText(entry, index)).join('\\n');
    _copyTextToClipboard(text).then(_showToast);
  }}

  function exportTimestamp() {{
    return new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  }}

  function downloadName(ext) {{
    const appName = {json.dumps(app_name)};
    return appName + '-' + exportTimestamp() + '.' + ext;
  }}

  function saveTxt() {{
    const text = lines.map((entry, index) => displayText(entry, index)).join('\\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], {{type: 'text/plain'}}));
    a.download = downloadName('txt');
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

    const prefixWidth = Math.max(0, ...lines.map((entry, index) => formatPrefix(index + 1, entry).length));
    const linesHtml = lines.map((entry, index) => {{
      const cls = entry.cls || '';
      const prefix = formatPrefix(index + 1, entry);
      const prefixSpan = prefix
        ? '<span class="perm-prefix" style="min-width:' + prefixWidth + 'ch">' + escHtml(prefix) + '</span>'
        : '';
      const content = cls === 'prompt-echo'
        ? renderPromptEcho(entry.text)
        : plainClsSet.has(cls)
          ? escHtml(entry.text)
          : ansi_up.ansi_to_html(entry.text);
      return '<span class="line' + (cls ? ' ' + cls : '') + '">' + prefixSpan
        + '<span class="perm-content">' + content + '</span></span>';
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
  .perm-prefix {{
    display: inline-block; margin-right: 14px;
    color: #505050; font-size: 10px; user-select: none;
    text-align: right; font-variant-numeric: tabular-nums;
  }}
  .perm-content {{ display: inline; }}
  .prompt-prefix {{ color: #6ab0f5; font-weight: 700; margin-right: 8px; }}
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

    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([html], {{type: 'text/html'}}));
    a.download = downloadName('html');
    a.click();
    URL.revokeObjectURL(a.href);
  }}
</script>
</body>
</html>"""
    return Response(html, mimetype="text/html")
