// ── Shared search logic ──

function _collectSearchTextNodes(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const parts = [];
  let offset = 0;
  let node;
  while ((node = walker.nextNode())) {
    const text = node.nodeValue || '';
    parts.push({ node, text, start: offset, end: offset + text.length });
    offset += text.length;
  }
  return parts;
}

function _highlightSearchLine(line, re) {
  const clone = line.cloneNode(true);
  const parts = _collectSearchTextNodes(clone);
  const text = parts.map(part => part.text).join('');
  if (!text) return false;

  const matches = [];
  re.lastIndex = 0;
  let match;
  while ((match = re.exec(text)) !== null) {
    if (!match[0]) {
      re.lastIndex++;
      continue;
    }
    matches.push({ start: match.index, end: match.index + match[0].length });
  }
  if (!matches.length) return false;

  let matchIdx = 0;
  for (const part of parts) {
    const { node, text: partText, start: partStart, end: partEnd } = part;
    let cursor = partStart;
    let localStart = 0;
    const frag = document.createDocumentFragment();

    while (cursor < partEnd) {
      while (matchIdx < matches.length && matches[matchIdx].end <= cursor) matchIdx++;
      const current = matches[matchIdx];
      if (!current || current.start >= partEnd) {
        frag.appendChild(document.createTextNode(partText.slice(localStart)));
        break;
      }

      if (cursor < current.start) {
        const plainEnd = Math.min(partEnd, current.start);
        const slice = partText.slice(localStart, localStart + (plainEnd - cursor));
        if (slice) frag.appendChild(document.createTextNode(slice));
        localStart += plainEnd - cursor;
        cursor = plainEnd;
        continue;
      }

      const markEnd = Math.min(partEnd, current.end);
      const mark = document.createElement('mark');
      mark.className = 'search-hl';
      mark.textContent = partText.slice(localStart, localStart + (markEnd - cursor));
      frag.appendChild(mark);
      localStart += markEnd - cursor;
      cursor = markEnd;
    }

    node.replaceWith(frag);
  }

  line.replaceWith(clone);
  return true;
}

function runSearch() {
  clearHighlights();
  searchMatches = [];
  searchMatchIdx = -1;
  const q = searchInput.value;
  if (!q) { searchCount.textContent = ''; return; }
  const out = getOutput(activeTabId);
  if (!out) return;
  const lines = out.querySelectorAll('.line');
  const flags = searchCaseSensitive ? 'g' : 'gi';
  const pattern = searchRegexMode ? q : escapeRegex(q);
  let re;
  try {
    re = new RegExp(pattern, flags);
  } catch(e) {
    searchCount.textContent = 'invalid regex';
    return;
  }
  lines.forEach(line => {
    _highlightSearchLine(line, re);
  });
  searchMatches = Array.from(out.querySelectorAll('mark.search-hl'));
  searchCount.textContent = searchMatches.length ? `1 / ${searchMatches.length}` : 'no matches';
  if (searchMatches.length) { searchMatchIdx = 0; highlightCurrent(); }
}

function navigateSearch(dir) {
  if (!searchMatches.length) return;
  searchMatchIdx = (searchMatchIdx + dir + searchMatches.length) % searchMatches.length;
  searchCount.textContent = `${searchMatchIdx + 1} / ${searchMatches.length}`;
  highlightCurrent();
}

function highlightCurrent() {
  searchMatches.forEach((m, i) => m.classList.toggle('current', i === searchMatchIdx));
  searchMatches[searchMatchIdx]?.scrollIntoView({ block: 'center' });
}

function clearHighlights() {
  const out = getOutput(activeTabId);
  if (!out) return;
  out.querySelectorAll('mark.search-hl').forEach(m => {
    m.replaceWith(document.createTextNode(m.textContent));
  });
}

function clearSearch() {
  clearHighlights();
  searchMatches = [];
  searchMatchIdx = -1;
  searchCount.textContent = '';
  searchInput.value = '';
}
