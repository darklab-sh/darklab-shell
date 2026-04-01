// ── Output search ──
let searchMatches = [];
let searchMatchIdx = -1;

function runSearch() {
  clearHighlights();
  searchMatches = [];
  searchMatchIdx = -1;
  const q = searchInput.value;
  if (!q) { searchCount.textContent = ''; return; }
  const out = getOutput(activeTabId);
  if (!out) return;
  const lines = out.querySelectorAll('.line');
  const re = new RegExp(escapeRegex(q), 'gi');
  lines.forEach(line => {
    const tmp = document.createElement('div');
    tmp.innerHTML = line.innerHTML;
    if (re.test(tmp.textContent)) {
      re.lastIndex = 0;
      line.innerHTML = line.innerHTML.replace(/<[^>]+>|[^<]+/g, seg => {
        if (seg.startsWith('<')) return seg;
        return seg.replace(re, match => {
          const mark = document.createElement('mark');
          mark.className = 'search-hl';
          mark.textContent = match;
          return mark.outerHTML;
        });
      });
    }
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
