// Files viewer format detection and preview payload shaping.
(function initWorkspaceViewerFormats(global) {
  function fileExt(path = '') {
    const name = String(path || '').split('/').filter(Boolean).pop() || '';
    const match = name.match(/\.([a-z0-9]+)$/i);
    return match ? match[1].toLowerCase() : '';
  }

  function looksLikeHttpResponse(text = '') {
    const raw = String(text || '').replace(/^\uFEFF/, '');
    return /^HTTP\/\d(?:\.\d)?\s+\d{3}/i.test(raw.trimStart());
  }

  function parseDelimitedLine(line = '', delimiter = ',') {
    const cells = [];
    let cell = '';
    let quoted = false;
    const text = String(line || '');
    for (let index = 0; index < text.length; index += 1) {
      const char = text[index];
      if (char === '"') {
        if (quoted && text[index + 1] === '"') {
          cell += '"';
          index += 1;
        } else {
          quoted = !quoted;
        }
      } else if (char === delimiter && !quoted) {
        cells.push(cell);
        cell = '';
      } else {
        cell += char;
      }
    }
    cells.push(cell);
    return cells;
  }

  function parseDelimited(text = '', delimiter = ',', { tableLimit = 250 } = {}) {
    const rows = String(text || '')
      .replace(/\r\n/g, '\n')
      .replace(/\r/g, '\n')
      .split('\n')
      .filter(line => line.length > 0)
      .slice(0, tableLimit + 1)
      .map(line => parseDelimitedLine(line, delimiter));
    const width = Math.max(0, ...rows.map(row => row.length));
    if (rows.length < 2 || width < 2) return null;
    return rows.map(row => {
      const next = row.slice();
      while (next.length < width) next.push('');
      return next;
    });
  }

  function formatXml(text = '') {
    const raw = String(text || '').trim();
    if (!raw || !/^<[\s\S]*>$/.test(raw)) return null;
    if (typeof DOMParser !== 'undefined') {
      try {
        const parsed = new DOMParser().parseFromString(raw, 'application/xml');
        if (parsed.querySelector('parsererror')) return null;
      } catch (_) {
        return null;
      }
    }
    const lines = raw
      .replace(/>\s*</g, '>\n<')
      .split('\n');
    let depth = 0;
    return lines.map(line => {
      const trimmed = line.trim();
      if (/^<\//.test(trimmed)) depth = Math.max(0, depth - 1);
      const formatted = `${'  '.repeat(depth)}${trimmed}`;
      if (/^<[^!?/][^>]*[^/]>\s*$/.test(trimmed) && !/^<([^>\s]+)[^>]*>.*<\/\1>$/.test(trimmed)) {
        depth += 1;
      }
      return formatted;
    }).join('\n');
  }

  function parseHttpResponse(text = '') {
    const normalized = String(text || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    const [head = '', ...bodyParts] = normalized.split(/\n\n/);
    const lines = head.split('\n').filter(Boolean);
    if (!lines.length || !/^HTTP\/\d(?:\.\d)?\s+\d{3}/i.test(lines[0])) return null;
    return {
      status: lines[0],
      headers: lines.slice(1).map(line => {
        const index = line.indexOf(':');
        return index >= 0
          ? { name: line.slice(0, index).trim(), value: line.slice(index + 1).trim() }
          : { name: line.trim(), value: '' };
      }),
      body: bodyParts.join('\n\n'),
    };
  }

  function formatJsonLines(text = '') {
    const rawLines = String(text || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
    const nonEmptyLines = rawLines.map(line => line.trim()).filter(Boolean);
    const formatted = [];
    for (const line of nonEmptyLines) {
      try {
        formatted.push(JSON.stringify(JSON.parse(line), null, 2));
      } catch (_) {
        return null;
      }
    }
    return nonEmptyLines.length ? formatted.join('\n') : null;
  }

  function looksLikeJsonLines(text = '') {
    const nonEmptyLines = String(text || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n')
      .map(line => line.trim())
      .filter(Boolean);
    if (nonEmptyLines.length < 2) return false;
    return nonEmptyLines.every(line => /^[{[]/.test(line));
  }

  function viewerPayload(path = '', text = '', options = {}) {
    const rawText = String(text || '');
    const trimmed = rawText.trim();
    const ext = fileExt(path);
    const http = looksLikeHttpResponse(rawText) ? parseHttpResponse(rawText) : null;
    if (http) return { text: rawText, format: 'http', http };
    if (ext === 'jsonl' || ext === 'ndjson' || looksLikeJsonLines(rawText)) {
      const jsonl = formatJsonLines(rawText);
      if (jsonl) return { text: jsonl, rawText, format: 'jsonl' };
      if (ext === 'jsonl' || ext === 'ndjson') {
        return { text: rawText, format: 'text', notice: 'Malformed JSONL; showing raw text.' };
      }
    }
    const looksJson = ext === 'json' || /^[{[]/.test(trimmed);
    if (looksJson) {
      try {
        return {
          text: JSON.stringify(JSON.parse(trimmed), null, 2),
          rawText,
          format: 'json',
        };
      } catch (_) {
        if (ext === 'json') return { text: rawText, format: 'text', notice: 'Malformed JSON; showing raw text.' };
      }
    }
    if (ext === 'csv' || ext === 'tsv') {
      const table = parseDelimited(rawText, ext === 'tsv' ? '\t' : ',', options);
      if (table) return { text: rawText, format: ext, table };
    }
    if (ext === 'xml' || /^<\?xml/.test(trimmed)) {
      const xml = formatXml(rawText);
      if (xml) return { text: xml, rawText, format: 'xml' };
      if (ext === 'xml') return { text: rawText, format: 'text', notice: 'Malformed XML; showing raw text.' };
    }
    return { text: rawText, format: 'text' };
  }

  function viewerRawText(payload) {
    return String(payload?.rawText ?? payload?.text ?? '');
  }

  global.DarklabWorkspaceViewerFormats = {
    viewerPayload,
    viewerRawText,
  };
})(typeof window !== 'undefined' ? window : this);
