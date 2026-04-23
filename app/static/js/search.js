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

function _highlightSearchLine(line, re, startMatchIdx) {
  // Search highlighting operates on a cloned line so the live transcript keeps
  // its original DOM structure until a match has actually been confirmed.
  // A single logical match that crosses an inline-element boundary (e.g. a
  // query that spans `.line-host`, ANSI-colour spans, or prompt wrappers)
  // cannot be wrapped in one `<mark>` — `<mark>` can't cross element
  // boundaries. Each segment gets its own `<mark>` but all segments of the
  // same logical match share a `data-search-match` index, so nav walks by
  // logical match, not DOM element.
  const clone = line.cloneNode(true);
  // Merge adjacent text nodes before walking — otherwise a prior
  // clearHighlights() pass leaves the line fragmented (mark replaced with a
  // sibling textNode, not merged with neighbours), and a fresh search emits
  // one `<mark>` per fragment instead of one per logical match, producing
  // visible pill-shape gaps that read as per-character highlighting.
  clone.normalize();
  const parts = _collectSearchTextNodes(clone);
  const text = parts.map(part => part.text).join('');
  if (!text) return 0;

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
  if (!matches.length) return 0;

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
      mark.dataset.searchMatch = String(startMatchIdx + matchIdx);
      mark.textContent = partText.slice(localStart, localStart + (markEnd - cursor));
      frag.appendChild(mark);
      localStart += markEnd - cursor;
      cursor = markEnd;
    }

    node.replaceWith(frag);
  }

  line.replaceWith(clone);
  return matches.length;
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
  let globalMatchIdx = 0;
  lines.forEach(line => {
    globalMatchIdx += _highlightSearchLine(line, re, globalMatchIdx);
  });
  // Group marks by logical match — a single match that crossed an inline
  // boundary produces multiple marks with the same data-search-match, and
  // nav/highlight should treat them as one.
  const groups = new Map();
  out.querySelectorAll('mark.search-hl').forEach(mark => {
    const idx = Number(mark.dataset.searchMatch);
    if (!groups.has(idx)) groups.set(idx, []);
    groups.get(idx).push(mark);
  });
  searchMatches = Array.from(groups.values());
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
  searchMatches.forEach((group, i) => {
    group.forEach(m => m.classList.toggle('current', i === searchMatchIdx));
  });
  searchMatches[searchMatchIdx]?.[0]?.scrollIntoView({ block: 'center' });
}

function clearHighlights() {
  const out = getOutput(activeTabId);
  if (!out) return;
  const touched = new Set();
  out.querySelectorAll('mark.search-hl').forEach(m => {
    const line = m.closest('.line');
    if (line) touched.add(line);
    m.replaceWith(document.createTextNode(m.textContent));
  });
  // Re-merge adjacent text nodes on every touched line so the next search
  // walks a clean DOM instead of an accumulation of single-character
  // fragments left behind by prior highlight cycles.
  touched.forEach(line => line.normalize());
}

function clearSearch() {
  clearHighlights();
  searchMatches = [];
  searchMatchIdx = -1;
  searchCount.textContent = '';
  searchInput.value = '';
}
