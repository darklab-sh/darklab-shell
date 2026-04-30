// ── Shared autocomplete logic ──

function _acItemText(item) {
  if (item && typeof item === 'object') {
    return String(item.label || item.value || '').trim();
  }
  return String(item || '').trim();
}

function _isAutocompleteBlockedByTerminalConfirm() {
  return typeof hasPendingTerminalConfirm === 'function' && hasPendingTerminalConfirm();
}

function _acItemInsertValue(item) {
  if (item && typeof item === 'object') {
    return String(item.insertValue || item.value || item.label || '').trim();
  }
  return String(item || '').trim();
}

// Like _acItemInsertValue but preserves the exact whitespace authors chose in
// the YAML, so an insertValue of "set " leaves the cursor after the space —
// the signal "ready to type an argument next". Only used at the insertion site.
function _acItemInsertText(item) {
  if (item && typeof item === 'object') {
    if (item.hintOnly) return '';
    const raw = item.insertValue != null ? item.insertValue : (item.value != null ? item.value : item.label);
    return String(raw || '');
  }
  return String(item || '');
}

// Arg-hints often use a placeholder like "<token>" to show what the next
// positional argument should be. Without this check, Tab on a single-item
// dropdown for that placeholder inserts the literal "<token>" string.
function _isPlaceholderValue(value) {
  return typeof value === 'string' && /^<[^<>\s][^<>]*>$/.test(value.trim());
}

function _acItemDescription(item) {
  if (!item || typeof item !== 'object') return '';
  return String(item.description || '').trim();
}

function _tokenContextFromText(value, cursorPos, offset = 0) {
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

function _autocompleteTokenContext(value, cursorPos) {
  return _tokenContextFromText(value, cursorPos, 0);
}

function _autocompletePipeContext(value, cursorPos) {
  const text = String(value || '');
  const cursor = Math.max(0, Math.min(typeof cursorPos === 'number' ? cursorPos : text.length, text.length));
  const firstPipeIndex = text.indexOf('|');
  if (firstPipeIndex < 0 || cursor <= firstPipeIndex) return null;

  const baseCommand = text.slice(0, firstPipeIndex).trim();
  if (!baseCommand) return null;

  const shellControlRe = /(^|[\s|])(?:&&|\|\||;|;;|>>?|<|&)(?=$|\s)/;
  if (shellControlRe.test(baseCommand)) return null;

  const stageSection = text.slice(firstPipeIndex + 1, cursor);
  const fullStageSection = text.slice(firstPipeIndex + 1);
  const rawStages = fullStageSection.split('|');
  const completedStageCount = stageSection.split('|').length - 1;
  const priorStages = rawStages.slice(0, completedStageCount);
  const invalidPriorStage = priorStages.some((stage) => {
    const stageText = String(stage || '').trim();
    if (!stageText || shellControlRe.test(stageText)) return true;
    const stageRoot = stageText.split(/\s+/, 1)[0].toLowerCase();
    const registry = _getAutocompleteRegistry();
    const spec = registry[stageRoot];
    return !spec || !spec.pipe_command;
  });
  if (invalidPriorStage) return null;

  const pipeIndex = text.lastIndexOf('|', cursor - 1);
  if (pipeIndex < 0) return null;
  const stageOffset = pipeIndex + 1;
  const stageText = text.slice(stageOffset);
  const stageCursor = Math.max(0, cursor - stageOffset);
  const ctx = _tokenContextFromText(stageText, stageCursor, stageOffset);
  return {
    ...ctx,
    baseCommand,
    pipeIndex,
  };
}

function _buildAutocompleteItem({ value, description = '', replaceStart, replaceEnd, insertValue = null, label = null, hintOnly = null }) {
  // If the caller didn't give us an insertValue and the value is a <placeholder>,
  // flag it as display-only so Tab doesn't insert the literal placeholder text.
  const resolvedHintOnly = hintOnly != null ? !!hintOnly : (insertValue == null && _isPlaceholderValue(value));
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

function _autocompleteSearchFields(item) {
  const fields = [_acItemInsertValue(item), _acItemText(item)]
    .map(value => String(value || '').trim())
    .filter(Boolean);
  return fields.filter((value, index) => fields.indexOf(value) === index);
}

function _autocompleteBoundaryIndex(value, query) {
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

function _autocompleteFuzzyMatchIndexes(value, query) {
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

function _scoreAutocompleteField(value, query) {
  const text = String(value || '').trim();
  const lower = text.toLowerCase();
  const q = String(query || '').toLowerCase();
  if (!text || !q) return null;
  if (lower === q) return 0;
  if (lower.startsWith(q)) return 100;

  const boundaryIndex = _autocompleteBoundaryIndex(text, q);
  if (boundaryIndex >= 0) {
    return 200 + boundaryIndex + Math.max(0, text.length - q.length) / 100;
  }

  const substringIndex = lower.indexOf(q);
  if (substringIndex >= 0) {
    return 300 + substringIndex + Math.max(0, text.length - q.length) / 100;
  }

  const fuzzyIndexes = _autocompleteFuzzyMatchIndexes(text, q);
  if (!fuzzyIndexes) return null;
  const first = fuzzyIndexes[0];
  const last = fuzzyIndexes[fuzzyIndexes.length - 1];
  const span = last - first + 1;
  const gapPenalty = Math.max(0, span - q.length);
  return 400 + first + (gapPenalty * 2) + Math.max(0, text.length - q.length) / 100;
}

function _scoreAutocompleteItem(item, query, originalIndex) {
  const q = String(query || '').trim().toLowerCase();
  if (!q) return {
    item,
    score: originalIndex,
    index: originalIndex,
  };
  const fieldScores = _autocompleteSearchFields(item)
    .map((field, fieldIndex) => {
      const score = _scoreAutocompleteField(field, q);
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

function _filterAutocompleteItems(items, query) {
  const q = String(query || '').trim().toLowerCase();
  if (!q) return items.slice();
  const concrete = [];
  const hintOnly = [];
  items.forEach(item => {
    if (item && typeof item === 'object' && item.hintOnly) hintOnly.push(item);
    else concrete.push(item);
  });
  const filteredConcrete = concrete
    .map((item, index) => _scoreAutocompleteItem(item, q, index))
    .filter(Boolean)
    .sort((left, right) => left.score - right.score || left.index - right.index)
    .map(result => result.item);
  return filteredConcrete.concat(hintOnly);
}

const RECENT_DOMAIN_LIMIT = 10;

function _recentDomainsSessionKey(sessionId = (typeof SESSION_ID !== 'undefined' ? SESSION_ID : 'session')) {
  return `recent_domains:${String(sessionId || 'session')}`;
}

function _readRecentDomains() {
  try {
    const raw = sessionStorage.getItem(_recentDomainsSessionKey());
    const parsed = JSON.parse(raw || '[]');
    return Array.isArray(parsed)
      ? parsed.map(value => String(value || '').trim().toLowerCase()).filter(Boolean).slice(0, RECENT_DOMAIN_LIMIT)
      : [];
  } catch (_) {
    return [];
  }
}

function _writeRecentDomains(items) {
  try {
    sessionStorage.setItem(_recentDomainsSessionKey(), JSON.stringify(items.slice(0, RECENT_DOMAIN_LIMIT)));
  } catch (_) { /* non-critical */ }
}

function _isDomainValue(value) {
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

function _normalizeRecentDomain(value) {
  const text = String(value || '').trim().toLowerCase().replace(/\.$/, '');
  return _isDomainValue(text) ? text : '';
}

function _itemLooksLikeDomainSlot(item) {
  return String(item && item.value_type || '').trim().toLowerCase() === 'domain';
}

function _itemLooksLikeWordlistSlot(item) {
  return String(item && item.value_type || '').trim().toLowerCase() === 'wordlist';
}

function _normalizeWordlistCategories(value) {
  if (Array.isArray(value)) {
    return value.map(item => String(item || '').trim().toLowerCase()).filter(Boolean);
  }
  const text = String(value || '').trim().toLowerCase();
  return text ? [text] : [];
}

function _domainArgHintTriggers(spec) {
  const argHints = spec && spec.arg_hints && typeof spec.arg_hints === 'object' ? spec.arg_hints : {};
  return Object.entries(argHints)
    .filter(([trigger, hints]) => trigger !== '__positional__' && Array.isArray(hints) && hints.some(_itemLooksLikeDomainSlot))
    .map(([trigger]) => String(trigger || ''));
}

function _wordlistArgHintTriggers(spec) {
  const argHints = spec && spec.arg_hints && typeof spec.arg_hints === 'object' ? spec.arg_hints : {};
  return Object.entries(argHints)
    .filter(([trigger, hints]) => trigger !== '__positional__' && Array.isArray(hints) && hints.some(_itemLooksLikeWordlistSlot))
    .map(([trigger]) => String(trigger || ''));
}

function _wordlistCategoriesFromHints(hints) {
  const categories = [];
  (Array.isArray(hints) ? hints : []).forEach((hint) => {
    _normalizeWordlistCategories(hint && hint.wordlist_category).forEach((category) => {
      if (!categories.includes(category)) categories.push(category);
    });
  });
  return categories;
}

function _concreteAutocompleteTokens(spec) {
  return new Set((spec && Array.isArray(spec.flags) ? spec.flags : [])
    .map(flag => String(flag && flag.value || '').toLowerCase())
    .filter(value => value && !value.startsWith('-') && !value.startsWith('+')));
}

function _positionalDomainSlots(spec) {
  const hints = spec && spec.arg_hints && Array.isArray(spec.arg_hints.__positional__)
    ? spec.arg_hints.__positional__
    : [];
  return hints.map(_itemLooksLikeDomainSlot);
}

function _positionalWordlistSlots(spec) {
  const hints = spec && spec.arg_hints && Array.isArray(spec.arg_hints.__positional__)
    ? spec.arg_hints.__positional__
    : [];
  return hints.map(hint => ({
    active: _itemLooksLikeWordlistSlot(hint),
    categories: _normalizeWordlistCategories(hint && hint.wordlist_category),
  }));
}

function _countCompletedPositionalValues(ctx, spec, contextSpec = {}) {
  const expectsValue = Array.isArray(spec && spec.expects_value) ? spec.expects_value : [];
  const expectsExact = new Set(expectsValue.map(token => String(token || '')));
  const expectsLower = new Set(expectsValue.map(token => String(token || '').toLowerCase()));
  const concreteTokens = _concreteAutocompleteTokens(spec);
  const subToken = contextSpec && contextSpec.subcommandToken ? contextSpec.subcommandToken : null;
  const completedTokens = ctx.tokens.filter(token => token.end <= ctx.tokenStart);
  let count = 0;
  let skipNext = false;
  for (let index = 1; index < completedTokens.length; index += 1) {
    const token = completedTokens[index];
    const tokenValue = String(token.value || '');
    const lower = tokenValue.toLowerCase();
    if (!tokenValue) continue;
    if (subToken && token.start === subToken.start && token.end === subToken.end) continue;
    if (skipNext) {
      skipNext = false;
      continue;
    }
    if (expectsExact.has(tokenValue) || expectsLower.has(lower)) {
      skipNext = true;
      continue;
    }
    if (tokenValue.startsWith('-') || tokenValue.startsWith('+') || concreteTokens.has(lower)) continue;
    count += 1;
  }
  return count;
}

function _isAutocompleteDomainValueSlot(ctx, spec, contextSpec = {}) {
  if (!spec) return false;
  const previous = String(ctx.previousToken || '');
  const previousLower = previous.toLowerCase();
  const domainTriggers = _domainArgHintTriggers(spec);
  if (domainTriggers.some(trigger => trigger === previous || trigger.toLowerCase() === previousLower)) return true;
  if (ctx.currentToken.startsWith('-') || ctx.currentToken.startsWith('+')) return false;
  const slots = _positionalDomainSlots(spec);
  if (!slots.length) return false;
  const index = _countCompletedPositionalValues(ctx, spec, contextSpec);
  return !!slots[index];
}

function _autocompleteWordlistValueSlot(ctx, spec, contextSpec = {}) {
  if (!spec) return { active: false, categories: [] };
  const previous = String(ctx.previousToken || '');
  const previousLower = previous.toLowerCase();
  const argHints = spec.arg_hints || {};
  const wordlistTriggers = _wordlistArgHintTriggers(spec);
  for (const trigger of wordlistTriggers) {
    if (trigger === previous || trigger.toLowerCase() === previousLower) {
      const hints = Object.prototype.hasOwnProperty.call(argHints, trigger)
        ? argHints[trigger]
        : argHints[trigger.toLowerCase()];
      return { active: true, categories: _wordlistCategoriesFromHints(hints) };
    }
  }
  if (ctx.currentToken.startsWith('-') || ctx.currentToken.startsWith('+')) return { active: false, categories: [] };
  const slots = _positionalWordlistSlots(spec);
  if (!slots.length) return { active: false, categories: [] };
  const index = _countCompletedPositionalValues(ctx, spec, contextSpec);
  return slots[index] || { active: false, categories: [] };
}

function _recentDomainAutocompleteItems(ctx) {
  return _readRecentDomains().map(domain => _buildAutocompleteItem({
    value: domain,
    description: 'Recent domain',
    replaceStart: ctx.tokenStart,
    replaceEnd: ctx.tokenEnd,
  }));
}

function _wordlistAutocompleteItems(ctx, categories = []) {
  const categorySet = new Set(_normalizeWordlistCategories(categories));
  const source = (typeof acWordlists !== 'undefined' && Array.isArray(acWordlists)) ? acWordlists : [];
  const filtered = source.filter((item) => {
    if (!categorySet.size) return true;
    const itemCategories = _normalizeWordlistCategories(item && (item.wordlist_category || item.category));
    return itemCategories.some(category => categorySet.has(category));
  });
  const items = filtered.map(item => _buildAutocompleteItem({
    value: String(item && item.value || ''),
    label: String(item && (item.label || item.value) || ''),
    description: String(item && item.description || 'Installed wordlist'),
    replaceStart: ctx.tokenStart,
    replaceEnd: ctx.tokenEnd,
  })).filter(item => item.value);
  return _filterAutocompleteItems(items, ctx && ctx.currentToken);
}

function _withRecentDomainSuggestions(ctx, baseItems) {
  const recentItems = _filterAutocompleteItems(_recentDomainAutocompleteItems(ctx), ctx.currentToken);
  if (!recentItems.length) return baseItems;
  const seen = new Set(recentItems.map(item => _acItemInsertValue(item).toLowerCase()));
  const rest = (Array.isArray(baseItems) ? baseItems : []).filter(item => {
    const key = _acItemInsertValue(item).toLowerCase();
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  return recentItems.concat(rest);
}

function _withWordlistSuggestions(ctx, baseItems, categories = []) {
  const wordlistItems = _wordlistAutocompleteItems(ctx, categories);
  if (!wordlistItems.length) return baseItems;
  const seen = new Set(wordlistItems.map(item => _acItemInsertValue(item).toLowerCase()));
  const rest = (Array.isArray(baseItems) ? baseItems : []).filter(item => {
    const key = _acItemInsertValue(item).toLowerCase();
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  return wordlistItems.concat(rest);
}

function _withTypedValueSlotSuggestions(ctx, baseItems, domainValueSlot, wordlistValueSlot) {
  if (wordlistValueSlot && wordlistValueSlot.active) {
    return _withWordlistSuggestions(ctx, baseItems, wordlistValueSlot.categories);
  }
  return domainValueSlot ? _withRecentDomainSuggestions(ctx, baseItems) : baseItems;
}

function rememberRecentDomainsFromCommand(command) {
  const text = String(command || '').trim();
  if (!text) return [];
  const registry = _getAutocompleteRegistry();
  const ctx = _autocompleteTokenContext(text, text.length);
  const rootSpec = ctx.commandRoot ? registry[ctx.commandRoot] : null;
  if (!rootSpec) return [];
  const contextSpec = _autocompleteSpecForContext(ctx, rootSpec);
  const spec = contextSpec.spec;
  if (!spec) return [];

  const domainTriggers = _domainArgHintTriggers(spec);
  const triggerExact = new Set(domainTriggers);
  const triggerLower = new Set(domainTriggers.map(trigger => trigger.toLowerCase()));
  const expectsValue = Array.isArray(spec.expects_value) ? spec.expects_value : [];
  const expectsExact = new Set(expectsValue.map(token => String(token || '')));
  const expectsLower = new Set(expectsValue.map(token => String(token || '').toLowerCase()));
  const concreteTokens = _concreteAutocompleteTokens(spec);
  const positionalSlots = _positionalDomainSlots(spec);
  const found = [];
  let skipNext = false;
  let positionalIndex = 0;

  for (let index = 1; index < ctx.tokens.length; index += 1) {
    const token = ctx.tokens[index];
    const tokenValue = String(token.value || '');
    const lower = tokenValue.toLowerCase();
    const previous = index > 0 ? String(ctx.tokens[index - 1].value || '') : '';
    const previousLower = previous.toLowerCase();
    if (!tokenValue) continue;
    if (contextSpec.subcommandToken && token.start === contextSpec.subcommandToken.start && token.end === contextSpec.subcommandToken.end) {
      continue;
    }
    if (triggerExact.has(previous) || triggerLower.has(previousLower)) {
      const domain = _normalizeRecentDomain(tokenValue);
      if (domain) found.push(domain);
      continue;
    }
    if (skipNext) {
      skipNext = false;
      continue;
    }
    if (expectsExact.has(tokenValue) || expectsLower.has(lower)) {
      skipNext = true;
      continue;
    }
    if (tokenValue.startsWith('-') || tokenValue.startsWith('+') || concreteTokens.has(lower)) continue;
    if (positionalSlots[positionalIndex]) {
      const domain = _normalizeRecentDomain(tokenValue);
      if (domain) found.push(domain);
    }
    positionalIndex += 1;
  }

  if (!found.length) return [];
  const existing = _readRecentDomains();
  const next = [];
  found.concat(existing).forEach(domain => {
    if (!domain || next.includes(domain)) return;
    next.push(domain);
  });
  _writeRecentDomains(next);
  return found;
}

function _mergeAutocompleteRegistry(base, overlay) {
  return Object.assign({}, base || {}, overlay || {});
}

function _workspaceAutocompleteHintsForFlag(spec, trigger) {
  const flags = Array.isArray(spec && spec.workspace_file_flags) ? spec.workspace_file_flags : [];
  const normalizedTrigger = String(trigger || '');
  if (!flags.some(flag => String(flag || '') === normalizedTrigger)) return null;
  if (typeof getWorkspaceAutocompleteFileHints !== 'function') return [];
  const hints = getWorkspaceAutocompleteFileHints();
  return Array.isArray(hints) ? hints : [];
}

function _getAutocompleteRegistry() {
  const yamlRegistry = (typeof acContextRegistry !== 'undefined' && acContextRegistry) || {};
  const runtimeRegistry = typeof getRuntimeAutocompleteContext === 'function'
    ? getRuntimeAutocompleteContext(yamlRegistry)
    : {};
  return _mergeAutocompleteRegistry(yamlRegistry, runtimeRegistry);
}

function _countCompletedPositionalArgs(ctx, spec) {
  const expectsValue = Array.isArray(spec.expects_value) ? spec.expects_value : [];
  const expectsValueExact = new Set(expectsValue.map(token => String(token || '')));
  const expectsValueLower = new Set(expectsValue.map(token => String(token || '').toLowerCase()));
  const completedTokens = ctx.tokens.filter(token => token.end <= ctx.tokenStart);
  let count = 0;
  let skipNext = false;

  for (let index = 1; index < completedTokens.length; index += 1) {
    const tokenValue = String(completedTokens[index].value || '');
    const tokenLower = tokenValue.toLowerCase();
    if (!tokenValue) continue;
    if (skipNext) {
      skipNext = false;
      continue;
    }
    if (expectsValueExact.has(tokenValue) || expectsValueLower.has(tokenLower)) {
      skipNext = true;
      continue;
    }
    if (tokenValue.startsWith('-') || tokenValue.startsWith('+')) continue;
    count += 1;
  }

  return count;
}

function _contextClosedByTokenArity(ctx, spec) {
  const closeAfter = spec && spec.close_after && typeof spec.close_after === 'object'
    ? spec.close_after
    : {};
  const entries = Object.entries(closeAfter);
  if (!entries.length || !ctx.atWhitespace) return false;
  const completedTokens = ctx.tokens.filter(token => token.end <= ctx.tokenStart);
  for (let index = 1; index < completedTokens.length; index += 1) {
    const token = String(completedTokens[index].value || '').toLowerCase();
    if (!Object.prototype.hasOwnProperty.call(closeAfter, token)) continue;
    const rawLimit = Number(closeAfter[token]);
    const limit = Number.isFinite(rawLimit) && rawLimit >= 0 ? rawLimit : 0;
    const following = completedTokens.slice(index + 1).filter(item => String(item.value || '').trim());
    if (following.length >= limit) return true;
  }
  return false;
}

function _mergeAutocompleteSpecForSubcommand(baseSpec, subSpec) {
  const merged = Object.assign({}, baseSpec || {}, subSpec || {});
  const flags = [];
  const seenFlags = new Set();
  [...((baseSpec && baseSpec.flags) || []), ...((subSpec && subSpec.flags) || [])].forEach(flag => {
    const key = String(flag && flag.value || '').toLowerCase();
    if (!key || seenFlags.has(key)) return;
    seenFlags.add(key);
    flags.push(flag);
  });
  const expectsValue = [];
  const seenValueTokens = new Set();
  [...((baseSpec && baseSpec.expects_value) || []), ...((subSpec && subSpec.expects_value) || [])].forEach(token => {
    const key = String(token || '');
    if (!key || seenValueTokens.has(key)) return;
    seenValueTokens.add(key);
    expectsValue.push(token);
  });
  const argHints = Object.assign({}, (baseSpec && baseSpec.arg_hints) || {}, (subSpec && subSpec.arg_hints) || {});
  if (subSpec && Object.prototype.hasOwnProperty.call(subSpec.arg_hints || {}, '__positional__')) {
    argHints.__positional__ = subSpec.arg_hints.__positional__;
  } else {
    argHints.__positional__ = [];
  }
  return Object.assign(merged, {
    flags,
    expects_value: expectsValue,
    arg_hints: argHints,
    subcommands: {},
    examples: (subSpec && subSpec.examples) || [],
  });
}

function _autocompleteSpecForContext(ctx, spec) {
  const subcommands = spec && spec.subcommands && typeof spec.subcommands === 'object'
    ? spec.subcommands
    : {};
  const names = Object.keys(subcommands);
  if (!names.length) return { spec, activeSubcommand: '', subcommandToken: null };
  for (let index = 1; index < ctx.tokens.length; index += 1) {
    const token = ctx.tokens[index];
    if (!token) continue;
    const isCurrentToken = token.start === ctx.tokenStart && token.end === ctx.tokenEnd;
    if (token.end > ctx.tokenStart && !isCurrentToken) continue;
    const value = String(token.value || '').toLowerCase();
    if (Object.prototype.hasOwnProperty.call(subcommands, value)) {
      return {
        spec: _mergeAutocompleteSpecForSubcommand(spec, subcommands[value]),
        activeSubcommand: value,
        subcommandToken: token,
      };
    }
  }
  return { spec, activeSubcommand: '', subcommandToken: null };
}

function _buildExampleAutocompleteItems(examples, { replaceStart, replaceEnd, completionPrefix }) {
  return (examples || []).map(ex => Object.assign(_buildAutocompleteItem({
    value: ex.value,
    description: ex.description || '',
    replaceStart,
    replaceEnd,
    insertValue: ex.value,
  }), { isExample: true, completionPrefix }));
}

function _collectAutocompleteExamples(spec) {
  const examples = [];
  const seen = new Set();

  function appendExample(example) {
    if (!example || typeof example !== 'object') return;
    const value = String(example.value || '').trim();
    if (!value) return;
    const key = value.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    examples.push(example);
  }

  ((spec && spec.examples) || []).forEach(appendExample);
  Object.values((spec && spec.subcommands) || {}).forEach(subSpec => {
    ((subSpec && subSpec.examples) || []).forEach(appendExample);
  });
  return examples;
}

function _filterExampleAutocompleteItems(items, typedPrefix) {
  const filtered = _filterAutocompleteItems(items, typedPrefix);
  const matched = new Set(filtered);
  return items.filter(item => matched.has(item));
}

function _buildUniqueSubcommandExampleAutocomplete(ctx, rootSpec) {
  const subcommands = rootSpec && rootSpec.subcommands && typeof rootSpec.subcommands === 'object'
    ? rootSpec.subcommands
    : {};
  if (!Object.keys(subcommands).length) return [];
  if (ctx.atWhitespace || ctx.tokens.length !== 2 || !ctx.currentToken || ctx.currentToken.startsWith('-')) return [];
  const secondToken = ctx.tokens[1];
  if (!secondToken || secondToken.start !== ctx.tokenStart || secondToken.end !== ctx.tokenEnd) return [];

  const matches = _filterAutocompleteItems(Object.keys(subcommands), ctx.currentToken);
  if (matches.length !== 1) return [];

  const subcommand = matches[0];
  const subSpec = subcommands[subcommand];
  if (!subSpec || !Array.isArray(subSpec.examples) || !subSpec.examples.length) return [];

  const typedPrefix = ctx.text.slice(0, ctx.tokenEnd);
  return _filterExampleAutocompleteItems(
    _buildExampleAutocompleteItems(subSpec.examples, {
      replaceStart: 0,
      replaceEnd: ctx.tokenEnd,
      completionPrefix: `${ctx.commandRoot} ${subcommand}`,
    }),
    typedPrefix,
  );
}

function _buildContextAutocomplete(ctx) {
  const registry = _getAutocompleteRegistry();
  const rootSpec = ctx.commandRoot ? registry[ctx.commandRoot] : null;
  const contextSpec = rootSpec ? _autocompleteSpecForContext(ctx, rootSpec) : { spec: null, activeSubcommand: '', subcommandToken: null };
  const spec = contextSpec.spec;

  if (!spec) {
    // Unknown command root — suggest matching command roots from the registry
    // while the user is still typing the first token (no trailing space yet).
    if (ctx.tokens.length <= 1 && !ctx.atWhitespace && ctx.commandRoot) {
      const matchingRoots = _filterAutocompleteItems(Object.keys(registry), ctx.commandRoot);
      // If exactly one command matches and it has examples, show those directly
      // so the user sees full invocation patterns while still typing the root.
      if (matchingRoots.length === 1) {
        const matchedSpec = registry[matchingRoots[0]];
        const examples = _collectAutocompleteExamples(matchedSpec);
        if (examples.length) {
          return _filterExampleAutocompleteItems(
            _buildExampleAutocompleteItems(examples, {
              replaceStart: ctx.tokenStart,
              replaceEnd: ctx.tokenEnd,
              completionPrefix: matchingRoots[0],
            }),
            ctx.currentToken,
          );
        }
      }
      return matchingRoots.map(root => _buildAutocompleteItem({
        value: root,
        description: '',
        replaceStart: ctx.tokenStart,
        replaceEnd: ctx.tokenEnd,
      }));
    }
    return [];
  }

  // Known command root being typed (no trailing space yet) — show examples so
  // users can discover full invocation patterns before they start adding flags.
  if (ctx.tokens.length === 1 && !ctx.atWhitespace) {
    const examples = _collectAutocompleteExamples(spec);
    if (!examples.length) return [];
    return _filterExampleAutocompleteItems(
      _buildExampleAutocompleteItems(examples, {
        replaceStart: ctx.tokenStart,
        replaceEnd: ctx.tokenEnd,
        completionPrefix: ctx.commandRoot,
      }),
      ctx.currentToken,
    );
  }

  const uniqueSubcommandExamples = _buildUniqueSubcommandExampleAutocomplete(ctx, rootSpec);
  if (uniqueSubcommandExamples.length) return uniqueSubcommandExamples;

  if (_contextClosedByTokenArity(ctx, spec)) return [];

  if (contextSpec.activeSubcommand && spec.examples && spec.examples.length) {
    const prefixEnd = ctx.atWhitespace ? ctx.cursor : ctx.tokenEnd;
    const typedPrefix = ctx.text.slice(0, prefixEnd);
    const subcommandIsCurrentToken = contextSpec.subcommandToken
      && ctx.tokenStart === contextSpec.subcommandToken.start
      && ctx.tokenEnd === contextSpec.subcommandToken.end;
    if (subcommandIsCurrentToken) {
      const examples = _filterExampleAutocompleteItems(
        _buildExampleAutocompleteItems(spec.examples, {
          replaceStart: 0,
          replaceEnd: prefixEnd,
          completionPrefix: `${ctx.commandRoot} ${contextSpec.activeSubcommand}`,
        }),
        typedPrefix,
      );
      if (examples.length) return examples;
    }
  }

  const currentIsFlag = ctx.currentToken.startsWith('-') || ctx.currentToken.startsWith('+');
  const argHints = spec.arg_hints || {};
  const previousLower = String(ctx.previousToken || '').toLowerCase();
  const argumentLimit = Number.isInteger(spec.argument_limit) && spec.argument_limit > 0
    ? spec.argument_limit
    : null;
  const allowPositionalHints = !argumentLimit
    || _countCompletedPositionalArgs(ctx, spec) < argumentLimit;

  const directHints = Object.prototype.hasOwnProperty.call(argHints, ctx.previousToken || '')
    ? argHints[ctx.previousToken || '']
    : (Object.prototype.hasOwnProperty.call(argHints, previousLower) ? argHints[previousLower] : null);
  const completedTokens = ctx.tokens.filter(token => token.end <= ctx.tokenStart);
  const sequenceArgHints = spec.sequence_arg_hints || {};
  const priorToken = completedTokens.length >= 2
    ? String(completedTokens[completedTokens.length - 2].value || '').toLowerCase()
    : '';
  const sequenceKey = `${priorToken} ${previousLower}`.trim();
  const sequenceHints = Object.prototype.hasOwnProperty.call(sequenceArgHints, sequenceKey)
    ? sequenceArgHints[sequenceKey]
    : null;
  const domainValueSlot = _isAutocompleteDomainValueSlot(ctx, spec, contextSpec);
  const wordlistValueSlot = _autocompleteWordlistValueSlot(ctx, spec, contextSpec);
  if (sequenceHints !== null) {
    const sequenceItems = _filterAutocompleteItems(
      sequenceHints.map(item => _buildAutocompleteItem({
        value: item.value,
        label: item.label || item.value,
        description: item.description || '',
        replaceStart: ctx.tokenStart,
        replaceEnd: ctx.tokenEnd,
        insertValue: item.insertValue != null ? item.insertValue : null,
      })),
      ctx.currentToken,
    );
    return _withTypedValueSlotSuggestions(ctx, sequenceItems, domainValueSlot, wordlistValueSlot);
  }
  if (directHints !== null) {
    const workspaceHints = _workspaceAutocompleteHintsForFlag(spec, ctx.previousToken || '');
    const hints = workspaceHints !== null ? workspaceHints : directHints;
    const directItems = _filterAutocompleteItems(
      hints.map(item => _buildAutocompleteItem({
        value: item.value,
        label: item.label || item.value,
        description: item.description || '',
        replaceStart: ctx.tokenStart,
        replaceEnd: ctx.tokenEnd,
        insertValue: item.insertValue != null ? item.insertValue : null,
      })),
      ctx.currentToken,
    );
    return _withTypedValueSlotSuggestions(ctx, directItems, domainValueSlot, wordlistValueSlot);
  }

  if (allowPositionalHints) {
    const concreteCommandTokens = (spec.flags || [])
      .filter(flag => {
        const value = String(flag.value || '');
        return value && !value.startsWith('-') && !value.startsWith('+');
      })
      .map(flag => _buildAutocompleteItem({
        value: flag.value,
        description: flag.description || '',
        replaceStart: ctx.tokenStart,
        replaceEnd: ctx.tokenEnd,
        insertValue: flag.value,
      }));
    const matchingCommandTokens = _filterAutocompleteItems(concreteCommandTokens, ctx.currentToken);
    if (matchingCommandTokens.length) return matchingCommandTokens;
  }

  const positionalHints = Object.prototype.hasOwnProperty.call(argHints, '__positional__')
    ? argHints.__positional__
    : [];

  if (!ctx.currentToken || currentIsFlag) {
    const usedFlags = new Set(
      ctx.tokens
        .filter(token => token.start !== ctx.tokenStart)
        .map(token => String(token.value || '').toLowerCase())
        .filter(token => token.startsWith('-') || token.startsWith('+'))
    );
    const flags = (spec.flags || [])
      .filter(flag => !usedFlags.has(String(flag.value || '').toLowerCase()))
      .map(flag => _buildAutocompleteItem({
        value: flag.value,
        description: flag.description || '',
        replaceStart: ctx.tokenStart,
        replaceEnd: ctx.tokenEnd,
        insertValue: flag.value + (ctx.atWhitespace ? '' : ''),
      }));
    const filteredFlags = _filterAutocompleteItems(flags, ctx.currentToken);
    if (!ctx.currentToken && ctx.atWhitespace && positionalHints.length && allowPositionalHints) {
      const positionalItems = positionalHints.map(item => _buildAutocompleteItem({
        value: item.value,
        label: item.label || item.value,
        description: item.description || '',
        replaceStart: ctx.tokenStart,
        replaceEnd: ctx.tokenEnd,
        insertValue: item.insertValue != null ? item.insertValue : null,
      }));
      return filteredFlags.concat(positionalItems);
    }
    return filteredFlags;
  }

  if (positionalHints.length && allowPositionalHints) {
    const positionalItems = _filterAutocompleteItems(
      positionalHints.map(item => _buildAutocompleteItem({
        value: item.value,
        label: item.label || item.value,
        description: item.description || '',
        replaceStart: ctx.tokenStart,
        replaceEnd: ctx.tokenEnd,
        insertValue: item.insertValue != null ? item.insertValue : null,
      })),
      ctx.currentToken,
    );
    return _withTypedValueSlotSuggestions(ctx, positionalItems, domainValueSlot, wordlistValueSlot);
  }
  return [];
}

function _buildPipeCommandAutocomplete(ctx, registry) {
  const items = Object.entries(registry)
    .filter(([, spec]) => spec && spec.pipe_command)
    .map(([root, spec]) => _buildAutocompleteItem({
      value: spec.pipe_insert_value || root,
      label: spec.pipe_label || spec.pipe_insert_value || root,
      description: spec.pipe_description || '',
      replaceStart: ctx.tokenStart,
      replaceEnd: ctx.tokenEnd,
      insertValue: spec.pipe_insert_value || root,
    }));
  return _filterAutocompleteItems(items, ctx.currentToken);
}

function _buildPipeAutocomplete(ctx) {
  const registry = _getAutocompleteRegistry();
  if (!ctx.commandRoot) return _buildPipeCommandAutocomplete(ctx, registry);

  const spec = registry[ctx.commandRoot];
  if (!spec || !spec.pipe_command) return [];
  return _buildContextAutocomplete(ctx);
}

function _buildFlatAutocomplete(value) {
  const q = String(value || '').trim();
  if (!q) return [];
  return _filterAutocompleteItems(((typeof acSuggestions !== 'undefined' && acSuggestions) || []), q).slice(0, 24);
}

function getAutocompleteMatches(value, cursorPos) {
  const text = String(value || '');
  const ctx = _autocompleteTokenContext(text, cursorPos);
  const pipeCtx = _autocompletePipeContext(text, cursorPos);
  const runtimeItems = !pipeCtx && typeof getRuntimeAutocompleteItems === 'function'
    ? getRuntimeAutocompleteItems(ctx, _buildAutocompleteItem, _filterAutocompleteItems)
    : [];
  let items = runtimeItems.length ? runtimeItems : (pipeCtx ? _buildPipeAutocomplete(pipeCtx) : _buildContextAutocomplete(ctx));
  if (!items.length && !pipeCtx) items = _buildFlatAutocomplete(text);

  if (!items.length) return [];
  if (typeof items[0] === 'string') {
    const q = text.trim().toLowerCase();
    if (items.some(item => String(item).toLowerCase() === q)) return [];
    return items;
  }

  // Hide the dropdown once the current token already equals the only suggestion.
  // Keep hint-only placeholders visible so the user still sees what argument
  // the command expects next, and keep exact flag matches visible so their
  // descriptions remain discoverable until the user types a trailing space.
  const singleItem = items[0];
  const singleItemIsFlag = String(singleItem && singleItem.value || '').startsWith('-')
    || String(singleItem && singleItem.value || '').startsWith('+');
  if (items.length === 1
      && !singleItem.hintOnly
      && !singleItemIsFlag
      && _acItemInsertValue(singleItem).toLowerCase() === ctx.currentToken.toLowerCase()) {
    return [];
  }
  return items;
}

function limitAutocompleteMatchesForDisplay(items, maxItems = 12) {
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

function _autocompleteHighlightedLabel(label, query) {
  const text = String(label || '');
  const q = String(query || '');
  if (!text || !q) return escapeHtml(text);

  const lower = text.toLowerCase();
  const lowerQuery = q.toLowerCase();
  const substringIndex = lower.indexOf(lowerQuery);
  if (substringIndex >= 0) {
    return escapeHtml(text.slice(0, substringIndex))
      + '<span class="ac-match">' + escapeHtml(text.slice(substringIndex, substringIndex + q.length)) + '</span>'
      + escapeHtml(text.slice(substringIndex + q.length));
  }

  const fuzzyIndexes = _autocompleteFuzzyMatchIndexes(text, q);
  if (!fuzzyIndexes) return escapeHtml(text);
  const matched = new Set(fuzzyIndexes);
  let html = '';
  for (let index = 0; index < text.length; index += 1) {
    const char = escapeHtml(text[index]);
    html += matched.has(index) ? `<span class="ac-match">${char}</span>` : char;
  }
  return html;
}

function _positionAutocomplete(itemsCount) {
  // Desktop anchors the dropdown to the prompt row; mobile anchors it above the
  // simplified composer so suggestions never hide behind the keyboard.
  if (!acDropdown) return false;
  const wrap = (typeof shellPromptWrap !== 'undefined' && shellPromptWrap) || acDropdown.parentElement;
  const composerHost = (typeof mobileComposerHost !== 'undefined' && mobileComposerHost) || null;
  const composerRow = (typeof mobileComposerRow !== 'undefined' && mobileComposerRow) || null;
  const prefix = wrap && wrap.querySelector ? wrap.querySelector('.prompt-prefix') : null;
  const mobileTerminalMode = !!(document.body && document.body.classList.contains('mobile-terminal-mode'));
  const mobileComposerMode = mobileTerminalMode;
  const anchor = mobileTerminalMode && composerRow ? composerRow : (mobileTerminalMode && composerHost ? composerHost : wrap);
  acDropdown.classList.toggle('ac-mobile', mobileTerminalMode);
  if (mobileTerminalMode) {
    const rect = anchor && typeof anchor.getBoundingClientRect === 'function'
      ? anchor.getBoundingClientRect()
      : { top: 0 };
    const rowH = 44;
    const desired = Math.min(8, Math.max(1, itemsCount)) * rowH + 10;
    // Cap at 360px max but don't further cap by available space — the dropdown
    // grows upward (bottom: calc(100% + 4px)) and the parent container clips it
    // if it would go off-screen. This ensures all items are visible without
    // requiring the user to scroll, which is unreliable on touch due to item
    // tap handlers competing with the native scroll gesture.
    const maxHeight = Math.max(88, Math.min(360, desired));
    acDropdown.style.position = 'absolute';
    acDropdown.style.left = '0';
    acDropdown.style.right = '0';
    acDropdown.style.width = '100%';
    acDropdown.style.minWidth = '0';
    acDropdown.style.maxHeight = `${Math.round(maxHeight)}px`;
    acDropdown.style.top = 'auto';
    acDropdown.style.bottom = 'calc(100% + 4px)';
    acDropdown.classList.add('ac-up');
    acDropdown.classList.add('dropdown-up');
    return true;
  }
  acDropdown.classList.remove('ac-mobile');
  const prefixOffset = mobileComposerMode ? 0 : (prefix ? Math.max(0, Math.ceil(prefix.getBoundingClientRect().width) + 8) : 0);
  const wrapRect = anchor && typeof anchor.getBoundingClientRect === 'function' ? anchor.getBoundingClientRect() : null;
  acDropdown.style.position = 'fixed';
  acDropdown.style.left = `${Math.max(0, Math.round((wrapRect ? wrapRect.left : 0) + prefixOffset))}px`;
  acDropdown.style.right = 'auto';
  acDropdown.style.minWidth = mobileComposerMode ? '0' : '24ch';
  acDropdown.style.width = mobileComposerMode && wrapRect ? `${Math.max(220, Math.round(wrapRect.width || 0))}px` : '';

  if (!anchor || typeof anchor.getBoundingClientRect !== 'function') {
    acDropdown.classList.remove('ac-up');
    acDropdown.classList.remove('dropdown-up');
    return false;
  }
  const rect = anchor.getBoundingClientRect();
  const rowH = 22;
  const desired = Math.min(10, Math.max(1, itemsCount)) * rowH + 10;
  const targetHeight = Math.max(88, Math.min(260, desired));
  const spaceBelow = Math.max(0, window.innerHeight - rect.bottom - 8);
  const spaceAbove = Math.max(0, rect.top - 8);
  const safetyPad = 20;
  const canFitBelow = spaceBelow >= (targetHeight + safetyPad);
  const canFitAbove = spaceAbove >= (targetHeight + safetyPad);
  const showAbove = mobileComposerMode || (!canFitBelow && (canFitAbove || spaceAbove > spaceBelow));
  acDropdown.classList.toggle('ac-up', showAbove);
  acDropdown.classList.toggle('dropdown-up', showAbove);
  const available = showAbove ? spaceAbove : spaceBelow;
  const edgeBuffer = mobileComposerMode ? 12 : (showAbove ? 20 : 30);
  const maxHeight = Math.max(0, Math.min(mobileComposerMode ? 200 : 260, available > edgeBuffer ? available - edgeBuffer : available));
  acDropdown.style.maxHeight = `${Math.round(maxHeight)}px`;
  if (showAbove) {
    acDropdown.style.top = 'auto';
    acDropdown.style.bottom = `${Math.max(8, Math.round(window.innerHeight - rect.top + 2))}px`;
  } else {
    acDropdown.style.top = `${Math.max(8, Math.round(rect.bottom + 2))}px`;
    acDropdown.style.bottom = 'auto';
  }
  return showAbove;
}

function _scrollAutocompleteActiveItem() {
  if (!acDropdown) return;
  const activeItem = acDropdown.querySelector('.ac-item.ac-active');
  if (!activeItem) return;

  const viewHeight = acDropdown.clientHeight || 0;
  const itemTop = typeof activeItem.offsetTop === 'number' ? activeItem.offsetTop : null;
  const itemHeight = typeof activeItem.offsetHeight === 'number' ? activeItem.offsetHeight : null;
  if (viewHeight > 0 && itemTop !== null && itemHeight !== null) {
    const itemBottom = itemTop + itemHeight;
    const viewTop = acDropdown.scrollTop || 0;
    const viewBottom = viewTop + viewHeight;
    const padding = 4;
    if (itemTop < viewTop + padding) {
      acDropdown.scrollTop = Math.max(0, itemTop - padding);
    } else if (itemBottom > viewBottom - padding) {
      acDropdown.scrollTop = Math.max(0, itemBottom - viewHeight + padding);
    }
    return;
  }

  if (typeof activeItem.scrollIntoView === 'function') {
    activeItem.scrollIntoView({ block: 'nearest' });
  }
}

function acShow(items) {
  if (_isAutocompleteBlockedByTerminalConfirm()) {
    acHide();
    return;
  }
  acDropdown.innerHTML = '';
  if (!items.length) { hideAcDropdown(); return; }
  _positionAutocomplete(items.length);
  if (acIndex >= items.length) acIndex = items.length - 1;
  const currentValue = (typeof getComposerValue === 'function')
    ? getComposerValue()
    : cmdInput.value;
  const currentCursor = (typeof getComposerState === 'function')
    ? getComposerState().selectionStart
    : (cmdInput && typeof cmdInput.selectionStart === 'number' ? cmdInput.selectionStart : currentValue.length);
  const tokenCtx = _autocompleteTokenContext(currentValue, currentCursor);
  const matchValue = (items.length && typeof items[0] === 'object') ? tokenCtx.currentToken : currentValue;
  const maxExampleLabelLen = items.reduce((max, s) =>
    (s && s.isExample ? Math.max(max, _acItemText(s).length) : max), 0);
  items.forEach((s, i) => {
    const div = document.createElement('div');
    div.className = 'ac-item dropdown-item dropdown-item-dense'
      + (i === acIndex ? ' ac-active dropdown-item-active' : '')
      + (s && s.isExample ? ' ac-example' : '');
    const label = _acItemText(s);
    const description = _acItemDescription(s);
    const val = String(matchValue || '');
    const main = document.createElement('span');
    main.className = 'ac-item-main';
    if (s && s.isExample && maxExampleLabelLen > 0) main.style.minWidth = maxExampleLabelLen + 'ch';
    main.innerHTML = _autocompleteHighlightedLabel(label, val);
    div.appendChild(main);
    if (description) {
      const desc = document.createElement('span');
      desc.className = 'ac-item-desc';
      desc.textContent = description;
      div.appendChild(desc);
    }
    div.addEventListener('mousedown', e => { e.preventDefault(); acAccept(s); });
    // touchstart must not call preventDefault so the container can scroll.
    // We detect taps by checking that the finger barely moved; swipes fall
    // through to the browser's native scroll handling.
    let _touchStartX = 0, _touchStartY = 0;
    div.addEventListener('touchstart', e => {
      const t = e.touches[0];
      _touchStartX = t ? t.clientX : 0;
      _touchStartY = t ? t.clientY : 0;
    }, { passive: true });
    div.addEventListener('touchend', e => {
      const t = e.changedTouches[0];
      const dx = t ? Math.abs(t.clientX - _touchStartX) : 99;
      const dy = t ? Math.abs(t.clientY - _touchStartY) : 99;
      if (dx < 10 && dy < 10) { e.preventDefault(); acAccept(s); }
    }, { passive: false });
    acDropdown.appendChild(div);
  });
  showAcDropdown();
  _positionAutocomplete(items.length);
  _scrollAutocompleteActiveItem();
}

function acHide() {
  hideAcDropdown();
  acIndex = -1;
}

function _getAutocompleteSharedPrefix(items) {
  if (!Array.isArray(items) || !items.length) return '';
  const completionPrefix = items[0] && typeof items[0] === 'object'
    ? String(items[0].completionPrefix || '').trim()
    : '';
  if (completionPrefix && items.every(item => (
    item && typeof item === 'object' && String(item.completionPrefix || '').trim() === completionPrefix
  ))) {
    return completionPrefix;
  }
  const first = _acItemInsertValue(items[0]);
  if (!first) return '';
  const lowerItems = items.map(item => _acItemInsertValue(item).toLowerCase());
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

function acExpandSharedPrefix(items) {
  if (!Array.isArray(items) || items.length < 2) return false;
  const currentValue = (typeof getComposerValue === 'function')
    ? getComposerValue()
    : (cmdInput ? cmdInput.value || '' : '');
  const firstItem = items[0];
  const sharedPrefix = _getAutocompleteSharedPrefix(items);
  if (!sharedPrefix) return false;
  if (firstItem && typeof firstItem === 'object') {
    const replaceStart = Number(firstItem.replaceStart);
    const replaceEnd = Number(firstItem.replaceEnd);
    if (!Number.isFinite(replaceStart) || !Number.isFinite(replaceEnd)) return false;
    const currentToken = currentValue.slice(replaceStart, replaceEnd);
    if (sharedPrefix.length <= currentToken.length) return false;
    if (!sharedPrefix.toLowerCase().startsWith(currentToken.toLowerCase())) return false;
    const next = currentValue.slice(0, replaceStart) + sharedPrefix + currentValue.slice(replaceEnd);
    const caret = replaceStart + sharedPrefix.length;
    setComposerValue(next, caret, caret);
    return true;
  }
  if (sharedPrefix.length <= currentValue.length) return false;
  if (!sharedPrefix.toLowerCase().startsWith(currentValue.toLowerCase())) return false;
  setComposerValue(sharedPrefix, sharedPrefix.length, sharedPrefix.length);
  return true;
}

function acAccept(s) {
  if (_isAutocompleteBlockedByTerminalConfirm()) {
    acHide();
    refocusComposerAfterAction({ preventScroll: true });
    return;
  }
  if (s && typeof s === 'object') {
    // Placeholder-only hints (e.g. "<token>") are display-only: Tab should hide
    // the dropdown, not insert the literal placeholder text into the prompt.
    if (s.hintOnly) {
      acHide();
      refocusComposerAfterAction({ preventScroll: true });
      return;
    }
    const currentValue = (typeof getComposerValue === 'function')
      ? getComposerValue()
      : (cmdInput ? cmdInput.value || '' : '');
    const insertValue = _acItemInsertText(s);
    const replaceStart = Number(s.replaceStart);
    const replaceEnd = Number(s.replaceEnd);
    if (typeof acSuppressInputOnce !== 'undefined') acSuppressInputOnce = true;
    if (Number.isFinite(replaceStart) && Number.isFinite(replaceEnd)) {
      const next = currentValue.slice(0, replaceStart) + insertValue + currentValue.slice(replaceEnd);
      const caret = replaceStart + insertValue.length;
      acHide();
      setComposerValue(next, caret, caret);
    } else {
      acHide();
      setComposerValue(insertValue, insertValue.length, insertValue.length);
    }
  } else {
    if (typeof acSuppressInputOnce !== 'undefined') acSuppressInputOnce = true;
    acHide();
    setComposerValue(s, s.length, s.length);
  }
  refocusComposerAfterAction({ preventScroll: true });
}
