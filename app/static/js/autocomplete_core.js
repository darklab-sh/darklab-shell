// ── Autocomplete pure helpers ────────────────────────────────────────────
// Loaded before autocomplete.js. Registry/runtime state and DOM rendering stay
// in autocomplete.js; matching, ranking, token context, and label transforms
// live here so tests can exercise a supported browser-visible seam.
var DarklabAutocompleteCore = (function (global) {
  const RECENT_DOMAIN_LIMIT = 10;

  function escapeHtmlText(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function itemText(item) {
    if (item && typeof item === 'object') {
      return String(item.label || item.value || '').trim();
    }
    return String(item || '').trim();
  }

  function itemInsertValue(item) {
    if (item && typeof item === 'object') {
      return String(item.insertValue || item.value || item.label || '').trim();
    }
    return String(item || '').trim();
  }

  function itemInsertText(item) {
    if (item && typeof item === 'object') {
      if (item.hintOnly) return '';
      const raw = item.insertValue != null ? item.insertValue : (item.value != null ? item.value : item.label);
      return String(raw || '');
    }
    return String(item || '');
  }

  function isPlaceholderValue(value) {
    return typeof value === 'string' && /^<[^<>\s][^<>]*>$/.test(value.trim());
  }

  function itemDescription(item) {
    if (!item || typeof item !== 'object') return '';
    return String(item.description || '').trim();
  }

  function tokenContextFromText(value, cursorPos, offset = 0) {
    const text = String(value || '');
    const cursor = Math.max(0, Math.min(typeof cursorPos === 'number' ? cursorPos : text.length, text.length));
    const tokens = [];
    const tokenRe = /\S+/g;
    let match;
    while ((match = tokenRe.exec(text)) !== null) {
      tokens.push({
        value: match[0],
        start: match.index,
        end: match.index + match[0].length,
      });
    }

    const containing = tokens.find(token => cursor > token.start && cursor <= token.end)
      || tokens.find(token => cursor === token.start && cursor === token.end);
    const atWhitespace = !containing;
    const tokenStart = containing ? containing.start : cursor;
    const tokenEnd = containing ? containing.end : cursor;
    const currentToken = containing ? containing.value : '';
    const beforeTokens = tokens.filter(token => token.end <= tokenStart);
    const previousToken = beforeTokens.length ? beforeTokens[beforeTokens.length - 1].value : null;
    const commandRoot = tokens.length ? String(tokens[0].value || '').toLowerCase() : '';
    return {
      text,
      cursor,
      tokens,
      currentToken,
      tokenStart: tokenStart + offset,
      tokenEnd: tokenEnd + offset,
      previousToken,
      commandRoot,
      atWhitespace,
    };
  }

  function buildItem({ value, description = '', replaceStart, replaceEnd, insertValue = null, label = null, hintOnly = null }) {
    const resolvedHintOnly = hintOnly != null ? !!hintOnly : (insertValue == null && isPlaceholderValue(value));
    return {
      value,
      label: label || value,
      description,
      replaceStart,
      replaceEnd,
      insertValue: resolvedHintOnly ? '' : (insertValue != null ? insertValue : value),
      hintOnly: resolvedHintOnly,
    };
  }

  function _searchFields(item) {
    const fields = [itemInsertValue(item), itemText(item)]
      .map(value => String(value || '').trim())
      .filter(Boolean);
    return fields.filter((value, index) => fields.indexOf(value) === index);
  }

  function boundaryIndex(value, query) {
    const text = String(value || '');
    const lower = text.toLowerCase();
    const q = String(query || '').toLowerCase();
    if (!text || !q) return -1;
    let index = lower.indexOf(q, 1);
    while (index >= 0) {
      const previous = text[index - 1];
      const current = text[index];
      const startsSegment = /[\s/\\._:@=-]/.test(previous || '');
      const startsCamel = /[a-z0-9]/.test(previous || '') && /[A-Z]/.test(current || '');
      if (startsSegment || startsCamel) return index;
      index = lower.indexOf(q, index + 1);
    }
    return -1;
  }

  function fuzzyMatchIndexes(value, query) {
    const text = String(value || '');
    const q = String(query || '').toLowerCase();
    if (!text || q.length < 2) return null;
    const lower = text.toLowerCase();
    const indexes = [];
    let from = 0;
    for (let index = 0; index < q.length; index += 1) {
      const found = lower.indexOf(q[index], from);
      if (found < 0) return null;
      indexes.push(found);
      from = found + 1;
    }
    return indexes;
  }

  function _scoreField(value, query) {
    const text = String(value || '').trim();
    const lower = text.toLowerCase();
    const q = String(query || '').toLowerCase();
    if (!text || !q) return null;
    if (lower === q) return 0;
    if (lower.startsWith(q)) return 100;

    const segmentIndex = boundaryIndex(text, q);
    if (segmentIndex >= 0) {
      return 200 + segmentIndex + Math.max(0, text.length - q.length) / 100;
    }

    const substringIndex = lower.indexOf(q);
    if (substringIndex >= 0) {
      return 300 + substringIndex + Math.max(0, text.length - q.length) / 100;
    }

    const fuzzyIndexes = fuzzyMatchIndexes(text, q);
    if (!fuzzyIndexes) return null;
    const first = fuzzyIndexes[0];
    const last = fuzzyIndexes[fuzzyIndexes.length - 1];
    const span = last - first + 1;
    const gapPenalty = Math.max(0, span - q.length);
    return 400 + first + (gapPenalty * 2) + Math.max(0, text.length - q.length) / 100;
  }

  function scoreItem(item, query, originalIndex) {
    const q = String(query || '').trim().toLowerCase();
    if (!q) return {
      item,
      score: originalIndex,
      index: originalIndex,
    };
    const fieldScores = _searchFields(item)
      .map((field, fieldIndex) => {
        const score = _scoreField(field, q);
        return score === null ? null : score + (fieldIndex * 0.5);
      })
      .filter(score => score !== null);
    if (!fieldScores.length) return null;
    return {
      item,
      score: Math.min(...fieldScores),
      index: originalIndex,
    };
  }

  function filterItems(items, query) {
    const q = String(query || '').trim().toLowerCase();
    if (!q) return items.slice();
    const concrete = [];
    const hintOnly = [];
    items.forEach(item => {
      if (item && typeof item === 'object' && item.hintOnly) hintOnly.push(item);
      else concrete.push(item);
    });
    const filteredConcrete = concrete
      .map((item, index) => scoreItem(item, q, index))
      .filter(Boolean)
      .sort((left, right) => left.score - right.score || left.index - right.index)
      .map(result => result.item);
    return filteredConcrete.concat(hintOnly);
  }

  function isDomainValue(value) {
    const text = String(value || '').trim().toLowerCase().replace(/\.$/, '');
    if (!text || text.length > 253 || text.includes('/') || text.includes(':') || text.includes('@')) return false;
    if (!text.includes('.')) return false;
    if (/^\d+(?:\.\d+){3}$/.test(text)) return false;
    const labels = text.split('.');
    return labels.length >= 2 && labels.every(label => (
      label.length >= 1
      && label.length <= 63
      && /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(label)
    ));
  }

  function normalizeRecentDomain(value) {
    const text = String(value || '').trim().toLowerCase().replace(/\.$/, '');
    return isDomainValue(text) ? text : '';
  }

  function normalizeRecentDomainList(items) {
    const next = [];
    (Array.isArray(items) ? items : []).forEach((item) => {
      const domain = normalizeRecentDomain(item);
      if (!domain || next.includes(domain)) return;
      next.push(domain);
    });
    return next.slice(0, RECENT_DOMAIN_LIMIT);
  }

  function normalizeWordlistCategories(value) {
    if (Array.isArray(value)) {
      return value.map(item => String(item || '').trim().toLowerCase()).filter(Boolean);
    }
    const text = String(value || '').trim().toLowerCase();
    return text ? [text] : [];
  }

  function limitItemsForDisplay(items, maxItems = 12) {
    if (!Array.isArray(items)) return [];
    const limit = Math.max(0, Number(maxItems) || 0);
    if (!limit) return [];
    if (items.length <= limit) return items.slice();

    const visible = items.slice(0, limit);
    if (visible.some(item => item && typeof item === 'object' && item.hintOnly)) {
      return visible;
    }

    const firstHiddenHint = items.slice(limit).find(item => item && typeof item === 'object' && item.hintOnly);
    if (!firstHiddenHint) return visible;

    return visible.slice(0, limit - 1).concat(firstHiddenHint);
  }

  function highlightedLabel(label, query) {
    const text = String(label || '');
    const q = String(query || '');
    if (!text || !q) return escapeHtmlText(text);

    const lower = text.toLowerCase();
    const lowerQuery = q.toLowerCase();
    const substringIndex = lower.indexOf(lowerQuery);
    if (substringIndex >= 0) {
      return escapeHtmlText(text.slice(0, substringIndex))
        + '<span class="ac-match">' + escapeHtmlText(text.slice(substringIndex, substringIndex + q.length)) + '</span>'
        + escapeHtmlText(text.slice(substringIndex + q.length));
    }

    const fuzzyIndexes = fuzzyMatchIndexes(text, q);
    if (!fuzzyIndexes) return escapeHtmlText(text);
    const matched = new Set(fuzzyIndexes);
    let html = '';
    for (let index = 0; index < text.length; index += 1) {
      const char = escapeHtmlText(text[index]);
      html += matched.has(index) ? `<span class="ac-match">${char}</span>` : char;
    }
    return html;
  }

  function sharedPrefix(items) {
    if (!Array.isArray(items) || !items.length) return '';
    const completionPrefix = items[0] && typeof items[0] === 'object'
      ? String(items[0].completionPrefix || '').trim()
      : '';
    if (completionPrefix && items.every(item => (
      item && typeof item === 'object' && String(item.completionPrefix || '').trim() === completionPrefix
    ))) {
      return completionPrefix;
    }
    const first = itemInsertValue(items[0]);
    if (!first) return '';
    const lowerItems = items.map(item => itemInsertValue(item).toLowerCase());
    let end = first.length;
    for (let i = 1; i < lowerItems.length; i += 1) {
      const candidate = lowerItems[i];
      let j = 0;
      const limit = Math.min(end, candidate.length);
      while (j < limit && lowerItems[0][j] === candidate[j]) j += 1;
      end = j;
      if (!end) return '';
    }
    return first.slice(0, end);
  }

  const api = Object.freeze({
    RECENT_DOMAIN_LIMIT,
    escapeHtmlText,
    itemText,
    itemInsertValue,
    itemInsertText,
    itemDescription,
    isPlaceholderValue,
    tokenContextFromText,
    buildItem,
    boundaryIndex,
    fuzzyMatchIndexes,
    scoreItem,
    filterItems,
    isDomainValue,
    normalizeRecentDomain,
    normalizeRecentDomainList,
    normalizeWordlistCategories,
    limitItemsForDisplay,
    highlightedLabel,
    sharedPrefix,
  });
  global.DarklabAutocompleteCore = api;
  return api;
})(typeof window !== 'undefined' ? window : globalThis);
