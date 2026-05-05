// ── Shared autocomplete logic ──
const autocompleteCore = typeof DarklabAutocompleteCore !== 'undefined' ? DarklabAutocompleteCore : null;

function _isAutocompleteBlockedByTerminalConfirm() {
  return typeof hasPendingTerminalConfirm === 'function' && hasPendingTerminalConfirm();
}

function _isAutocompleteBlockedByActiveRun() {
  return typeof isActiveTabRunning === 'function' && isActiveTabRunning();
}

function _autocompleteTokenContext(value, cursorPos) {
  return autocompleteCore.tokenContextFromText(value, cursorPos, 0);
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
  return autocompleteCore.tokenContextFromText(stageText, stageCursor, stageOffset);
}

function _hintsToItems(hints, ctx, options = {}) {
  const replaceStart = typeof options.replaceStart === 'number' ? options.replaceStart : ctx.tokenStart;
  const replaceEnd = typeof options.replaceEnd === 'number' ? options.replaceEnd : ctx.tokenEnd;
  const matchQuery = typeof options.matchQuery === 'string' ? options.matchQuery : null;
  return (Array.isArray(hints) ? hints : []).map((item) => {
    const isObject = item && typeof item === 'object';
    const value = isObject ? item.value : item;
    const hintOnly = isObject && item.hintOnly != null
      ? item.hintOnly
      : (isObject && item.hint_only != null ? item.hint_only : null);
    const built = autocompleteCore.buildItem({
      value,
      label: isObject && item.label != null ? item.label : value,
      description: isObject ? (item.description || '') : '',
      replaceStart,
      replaceEnd,
      insertValue: isObject && item.insertValue != null ? item.insertValue : null,
      hintOnly,
    });
    if (matchQuery !== null) built.matchQuery = matchQuery;
    return built;
  });
}

const RECENT_DOMAIN_LIMIT = autocompleteCore.RECENT_DOMAIN_LIMIT;
let acRecentDomains = [];
const acRecentDomainPersistPromises = new Set();

function _readRecentDomains() {
  return acRecentDomains.slice(0, RECENT_DOMAIN_LIMIT);
}

function setRecentDomains(items) {
  acRecentDomains = autocompleteCore.normalizeRecentDomainList(items);
  return _readRecentDomains();
}

function loadRecentDomains() {
  if (typeof apiFetch !== 'function') return Promise.resolve(_readRecentDomains());
  return apiFetch('/session/recent-domains')
    .then(resp => (resp && typeof resp.json === 'function' ? resp.json() : {}))
    .then((data) => {
      if (data && Array.isArray(data.domains)) return setRecentDomains(data.domains);
      return _readRecentDomains();
    })
    .catch((err) => {
      if (typeof logClientError === 'function') logClientError('failed to load recent domains', err);
      return _readRecentDomains();
    });
}

function _persistRecentDomains(items) {
  const domains = autocompleteCore.normalizeRecentDomainList(items);
  if (!domains.length || typeof apiFetch !== 'function') return Promise.resolve(null);
  const request = apiFetch('/session/recent-domains', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ domains }),
  })
    .then(resp => (resp && typeof resp.json === 'function' ? resp.json() : null))
    .then((data) => {
      if (data && Array.isArray(data.domains)) setRecentDomains(data.domains);
      return data;
    })
    .catch((err) => {
      if (typeof logClientError === 'function') logClientError('failed to save recent domains', err);
      return null;
    });
  const tracked = request.finally(() => {
    acRecentDomainPersistPromises.delete(tracked);
  });
  acRecentDomainPersistPromises.add(tracked);
  return tracked;
}

function flushRecentDomains() {
  if (!acRecentDomainPersistPromises.size) return Promise.resolve([]);
  return Promise.all(Array.from(acRecentDomainPersistPromises)).catch(() => []);
}

function _itemValueTypeIs(item, type) {
  return String(item && item.value_type || '').trim().toLowerCase() === String(type || '').trim().toLowerCase();
}

function _autocompleteSpecRequiresWorkspace(spec) {
  const feature = spec && (spec.feature_required || spec.requires_feature || spec.feature);
  const features = Array.isArray(feature) ? feature : [feature];
  return features.some(item => String(item || '').trim().toLowerCase() === 'workspace');
}

function _wordlistCategoriesFromHints(hints) {
  const categories = [];
  (Array.isArray(hints) ? hints : []).forEach((hint) => {
    autocompleteCore.normalizeWordlistCategories(hint && hint.wordlist_category).forEach((category) => {
      if (!categories.includes(category)) categories.push(category);
    });
  });
  return categories;
}

const AUTOCOMPLETE_VALUE_TYPE_HANDLERS = {
  domain: {
    emptySlot: false,
    slotFromHints: hints => (Array.isArray(hints) ? hints : []).some(hint => _itemValueTypeIs(hint, 'domain')),
    applySuggestions: (ctx, baseItems) => _withRecentDomainSuggestions(ctx, baseItems),
  },
  wordlist: {
    emptySlot: { active: false, categories: [] },
    slotFromHints: (hints) => {
      const list = Array.isArray(hints) ? hints : [];
      if (!list.some(hint => _itemValueTypeIs(hint, 'wordlist'))) return { active: false, categories: [] };
      return { active: true, categories: _wordlistCategoriesFromHints(list) };
    },
    applySuggestions: (ctx, baseItems, slot) => (
      slot && slot.active ? _withWordlistSuggestions(ctx, baseItems, slot.categories) : baseItems
    ),
  },
  target: {
    sourceHints: (spec, hints) => {
      if (!_autocompleteSpecRequiresWorkspace(spec)) return null;
      if (!(Array.isArray(hints) && hints.some(hint => _itemValueTypeIs(hint, 'target')))) return null;
      return _workspaceAutocompleteEntryHints();
    },
  },
};

function _valueTypeHandler(type) {
  return AUTOCOMPLETE_VALUE_TYPE_HANDLERS[String(type || '').trim().toLowerCase()] || null;
}

function _emptyValueTypeSlot(type) {
  const handler = _valueTypeHandler(type);
  const empty = handler && Object.prototype.hasOwnProperty.call(handler, 'emptySlot') ? handler.emptySlot : false;
  if (empty && typeof empty === 'object') return Array.isArray(empty) ? empty.slice() : Object.assign({}, empty);
  return empty;
}

function _valueTypeSlotFromHints(type, hints) {
  const handler = _valueTypeHandler(type);
  return handler && typeof handler.slotFromHints === 'function'
    ? handler.slotFromHints(hints)
    : _emptyValueTypeSlot(type);
}

function _valueTypeSourceHints(type, spec, hints) {
  const handler = _valueTypeHandler(type);
  return handler && typeof handler.sourceHints === 'function'
    ? handler.sourceHints(spec, hints)
    : null;
}

function _argHintsForTrigger(argHints, trigger) {
  if (Object.prototype.hasOwnProperty.call(argHints, trigger)) return argHints[trigger];
  const lower = String(trigger || '').toLowerCase();
  return Object.prototype.hasOwnProperty.call(argHints, lower) ? argHints[lower] : [];
}

function _argHintTriggersForValueType(spec, type) {
  const argHints = spec && spec.arg_hints && typeof spec.arg_hints === 'object' ? spec.arg_hints : {};
  return Object.entries(argHints)
    .filter(([trigger, hints]) => (
      trigger !== '__positional__'
      && Array.isArray(hints)
      && hints.some(hint => _itemValueTypeIs(hint, type))
    ))
    .map(([trigger]) => String(trigger || ''));
}

function _concreteAutocompleteTokens(spec) {
  return new Set((spec && Array.isArray(spec.flags) ? spec.flags : [])
    .map(flag => String(flag && flag.value || '').toLowerCase())
    .filter(value => value && !value.startsWith('-') && !value.startsWith('+')));
}

function _positionalHintSlotsForValueType(spec, type) {
  const hints = spec && spec.arg_hints && Array.isArray(spec.arg_hints.__positional__)
    ? spec.arg_hints.__positional__
    : [];
  return hints.map(hint => _valueTypeSlotFromHints(type, [hint]));
}

function _walkAutocompletePositionalValues(ctx, spec, contextSpec = {}, visitor = () => {}, options = {}) {
  const expectsValue = Array.isArray(spec && spec.expects_value) ? spec.expects_value : [];
  const expectsExact = new Set(expectsValue.map(token => String(token || '')));
  const expectsLower = new Set(expectsValue.map(token => String(token || '').toLowerCase()));
  const concreteTokens = options.skipConcreteTokens ? _concreteAutocompleteTokens(spec) : new Set();
  const subToken = contextSpec && contextSpec.subcommandToken ? contextSpec.subcommandToken : null;
  const tokens = Array.isArray(options.tokens)
    ? options.tokens
    : ctx.tokens.filter(token => token.end <= ctx.tokenStart);
  const triggerExact = new Set((options.triggers || []).map(trigger => String(trigger || '')));
  const triggerLower = new Set((options.triggers || []).map(trigger => String(trigger || '').toLowerCase()));
  let skipNext = false;
  let positionalIndex = 0;
  for (let index = 1; index < tokens.length; index += 1) {
    const token = tokens[index];
    const tokenValue = String(token.value || '');
    const lower = tokenValue.toLowerCase();
    const previous = index > 0 ? String(tokens[index - 1].value || '') : '';
    const previousLower = previous.toLowerCase();
    if (!tokenValue) continue;
    if (subToken && token.start === subToken.start && token.end === subToken.end) continue;
    if (triggerExact.has(previous) || triggerLower.has(previousLower)) {
      visitor({
        triggered: true,
        token,
        tokenValue,
        lower,
        previous,
        previousLower,
        positionalIndex,
      });
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
    visitor({
      triggered: false,
      token,
      tokenValue,
      lower,
      previous,
      previousLower,
      positionalIndex,
    });
    positionalIndex += 1;
  }
}

function _countCompletedPositionalValues(ctx, spec, contextSpec = {}) {
  let count = 0;
  _walkAutocompletePositionalValues(ctx, spec, contextSpec, () => {
    count += 1;
  }, {
    skipConcreteTokens: true,
  });
  return count;
}

function _countCompletedPositionalArgs(ctx, spec) {
  let count = 0;
  _walkAutocompletePositionalValues(ctx, spec, {}, () => {
    count += 1;
  });
  return count;
}

function _collectRecentDomainsFromPositionalValues(ctx, spec, contextSpec, triggers) {
  const positionalSlots = _positionalHintSlotsForValueType(spec, 'domain');
  const found = [];
  _walkAutocompletePositionalValues(ctx, spec, contextSpec, ({ triggered, tokenValue, positionalIndex }) => {
    if (triggered || positionalSlots[positionalIndex]) {
      const domain = autocompleteCore.normalizeRecentDomain(tokenValue);
      if (domain) found.push(domain);
    }
  }, {
    tokens: ctx.tokens,
    triggers,
    skipConcreteTokens: true,
  });
  return found;
}

function _storeRecentDomains(found) {
  if (!found.length) return [];
  const existing = _readRecentDomains();
  const next = [];
  found.concat(existing).forEach(domain => {
    if (!domain || next.includes(domain)) return;
    next.push(domain);
  });
  setRecentDomains(next);
  _persistRecentDomains(found);
  return found;
}

function _autocompleteValueTypeSlot(ctx, spec, contextSpec = {}, type = '') {
  if (!spec) return _emptyValueTypeSlot(type);
  const previous = String(ctx.previousToken || '');
  const previousLower = previous.toLowerCase();
  const argHints = spec.arg_hints || {};
  const triggers = _argHintTriggersForValueType(spec, type);
  for (const trigger of triggers) {
    if (trigger === previous || trigger.toLowerCase() === previousLower) {
      return _valueTypeSlotFromHints(type, _argHintsForTrigger(argHints, trigger));
    }
  }
  if (ctx.currentToken.startsWith('-') || ctx.currentToken.startsWith('+')) return _emptyValueTypeSlot(type);
  const slots = _positionalHintSlotsForValueType(spec, type);
  if (!slots.length) return _emptyValueTypeSlot(type);
  const index = _countCompletedPositionalValues(ctx, spec, contextSpec);
  return slots[index] || _emptyValueTypeSlot(type);
}

function _autocompleteValueTypeSlots(ctx, spec, contextSpec = {}) {
  return {
    domain: _autocompleteValueTypeSlot(ctx, spec, contextSpec, 'domain'),
    wordlist: _autocompleteValueTypeSlot(ctx, spec, contextSpec, 'wordlist'),
  };
}

function _recentDomainAutocompleteItems(ctx) {
  return _readRecentDomains().map(domain => autocompleteCore.buildItem({
    value: domain,
    description: 'Recent domain',
    replaceStart: ctx.tokenStart,
    replaceEnd: ctx.tokenEnd,
  }));
}

function _wordlistAutocompleteItems(ctx, categories = []) {
  const categorySet = new Set(autocompleteCore.normalizeWordlistCategories(categories));
  const source = (typeof acWordlists !== 'undefined' && Array.isArray(acWordlists)) ? acWordlists : [];
  const filtered = source.filter((item) => {
    if (!categorySet.size) return true;
    const itemCategories = autocompleteCore.normalizeWordlistCategories(item && (item.wordlist_category || item.category));
    return itemCategories.some(category => categorySet.has(category));
  });
  const items = filtered.map(item => autocompleteCore.buildItem({
    value: String(item && item.value || ''),
    label: String(item && (item.label || item.value) || ''),
    description: String(item && item.description || 'Installed wordlist'),
    replaceStart: ctx.tokenStart,
    replaceEnd: ctx.tokenEnd,
  })).filter(item => item.value);
  return autocompleteCore.filterItems(items, ctx && ctx.currentToken);
}

function _prependDedupedItems(specialItems, baseItems) {
  if (!Array.isArray(specialItems) || !specialItems.length) return baseItems;
  const seen = new Set(specialItems.map(item => autocompleteCore.itemInsertValue(item).toLowerCase()));
  const rest = (Array.isArray(baseItems) ? baseItems : []).filter(item => {
    const key = autocompleteCore.itemInsertValue(item).toLowerCase();
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  return specialItems.concat(rest);
}

function _withRecentDomainSuggestions(ctx, baseItems) {
  const recentItems = autocompleteCore.filterItems(_recentDomainAutocompleteItems(ctx), ctx.currentToken);
  return _prependDedupedItems(recentItems, baseItems);
}

function _withWordlistSuggestions(ctx, baseItems, categories = []) {
  const wordlistItems = _wordlistAutocompleteItems(ctx, categories);
  return _prependDedupedItems(wordlistItems, baseItems);
}

function _withTypedValueSlotSuggestions(ctx, baseItems, valueSlots = {}) {
  const wordlistHandler = _valueTypeHandler('wordlist');
  if (wordlistHandler && valueSlots.wordlist && valueSlots.wordlist.active) {
    return wordlistHandler.applySuggestions(ctx, baseItems, valueSlots.wordlist);
  }
  const domainHandler = _valueTypeHandler('domain');
  if (domainHandler && valueSlots.domain) {
    return domainHandler.applySuggestions(ctx, baseItems, valueSlots.domain);
  }
  return baseItems;
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

  return _storeRecentDomains(
    _collectRecentDomainsFromPositionalValues(ctx, spec, contextSpec, _argHintTriggersForValueType(spec, 'domain')),
  );
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

function _workspaceAutocompleteEntryHints() {
  const fileHints = typeof getWorkspaceAutocompleteFileHints === 'function'
    ? getWorkspaceAutocompleteFileHints()
    : [];
  const directoryHints = typeof getWorkspaceAutocompleteDirectoryHints === 'function'
    ? getWorkspaceAutocompleteDirectoryHints()
    : [];
  return [
    ...(Array.isArray(fileHints) ? fileHints : []),
    ...(Array.isArray(directoryHints) ? directoryHints : []),
  ];
}

function _workspaceAutocompleteHintsForTargetSlot(spec, hints) {
  return _valueTypeSourceHints('target', spec, hints);
}

function _autocompleteWorkspacePathKindFromArray(kinds, index) {
  if (!Array.isArray(kinds) || index < 0 || index >= kinds.length) return '';
  const kind = String(kinds[index] || '').trim().toLowerCase();
  return ['file', 'directory', 'any'].includes(kind) ? kind : '';
}

function _autocompleteWorkspacePathKind(ctx, spec) {
  const pathKinds = spec && spec.workspace_path_arg_kinds;
  if (!pathKinds || typeof pathKinds !== 'object') return '';
  const completedTokens = ctx.tokens.filter(token => token.end <= ctx.tokenStart);
  for (let index = 1; index < completedTokens.length; index += 1) {
    const trigger = String(completedTokens[index].value || '').toLowerCase();
    const kinds = pathKinds[trigger];
    if (!Array.isArray(kinds)) continue;
    const argIndex = completedTokens
      .slice(index + 1)
      .filter(token => {
        const value = String(token && token.value || '');
        return value && !value.startsWith('-') && !value.startsWith('+');
      })
      .length;
    return _autocompleteWorkspacePathKindFromArray(kinds, argIndex);
  }
  return _autocompleteWorkspacePathKindFromArray(
    pathKinds.__positional__,
    _countCompletedPositionalArgs(ctx, spec),
  );
}

function _workspaceAutocompletePathHintsForContext(ctx, spec) {
  if (!String(ctx.currentToken || '').includes('/')) return null;
  const kind = _autocompleteWorkspacePathKind(ctx, spec);
  if (!kind) return null;
  if (typeof getWorkspaceAutocompletePathHints !== 'function') return [];
  const hints = getWorkspaceAutocompletePathHints(kind, ctx.currentToken);
  return Array.isArray(hints) ? hints : [];
}

function _workspaceAutocompletePathFilterQuery(ctx) {
  const token = String(ctx && ctx.currentToken || '');
  const slashIndex = token.lastIndexOf('/');
  return slashIndex >= 0 ? token.slice(slashIndex + 1) : token;
}

function _autocompleteSpecHasWorkspacePathKinds(spec) {
  return !!(spec && spec.workspace_path_arg_kinds && typeof spec.workspace_path_arg_kinds === 'object');
}

function _resolveAutocompleteHintSource(ctx, spec, baseHints, options = {}) {
  const workspaceFlag = Object.prototype.hasOwnProperty.call(options, 'workspaceFlag')
    ? options.workspaceFlag
    : null;
  const workspaceHints = workspaceFlag != null
    ? _workspaceAutocompleteHintsForFlag(spec, workspaceFlag)
    : null;
  if (workspaceHints !== null) {
    return {
      hints: workspaceHints,
      filterQuery: ctx.currentToken,
      workspacePathActive: false,
    };
  }

  const workspacePathHints = _workspaceAutocompletePathHintsForContext(ctx, spec);
  if (workspacePathHints !== null) {
    return {
      hints: workspacePathHints,
      filterQuery: _workspaceAutocompletePathFilterQuery(ctx),
      workspacePathActive: true,
    };
  }

  const allowWorkspaceTarget = options.allowWorkspaceTarget !== false;
  const workspaceTargetHints = allowWorkspaceTarget && !_autocompleteSpecHasWorkspacePathKinds(spec)
    ? _workspaceAutocompleteHintsForTargetSlot(spec, baseHints)
    : null;
  return {
    hints: workspaceTargetHints !== null ? workspaceTargetHints : baseHints,
    filterQuery: ctx.currentToken,
    workspacePathActive: false,
  };
}

function _getAutocompleteRegistry() {
  const yamlRegistry = (typeof acContextRegistry !== 'undefined' && acContextRegistry) || {};
  const runtimeRegistry = typeof getRuntimeAutocompleteContext === 'function'
    ? getRuntimeAutocompleteContext(yamlRegistry)
    : {};
  return _mergeAutocompleteRegistry(yamlRegistry, runtimeRegistry);
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
  return (examples || []).map(ex => Object.assign(autocompleteCore.buildItem({
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
  const filtered = autocompleteCore.filterItems(items, typedPrefix);
  // Keep YAML-author order for examples while reusing the normal matcher to
  // decide which examples are visible.
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

  const matches = autocompleteCore.filterItems(Object.keys(subcommands), ctx.currentToken);
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
      const matchingRoots = autocompleteCore.filterItems(Object.keys(registry), ctx.commandRoot);
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
      return matchingRoots.map(root => autocompleteCore.buildItem({
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
  const valueSlots = _autocompleteValueTypeSlots(ctx, spec, contextSpec);
  if (sequenceHints !== null) {
    const resolved = _resolveAutocompleteHintSource(ctx, spec, sequenceHints, {
      allowWorkspaceTarget: false,
    });
    const sequenceItems = autocompleteCore.filterItems(
      _hintsToItems(resolved.hints, ctx, { matchQuery: resolved.filterQuery }),
      resolved.filterQuery,
    );
    return _withTypedValueSlotSuggestions(ctx, sequenceItems, valueSlots);
  }
  if (directHints !== null) {
    const resolved = _resolveAutocompleteHintSource(ctx, spec, directHints, {
      workspaceFlag: ctx.previousToken || '',
    });
    const directItems = autocompleteCore.filterItems(
      _hintsToItems(resolved.hints, ctx, { matchQuery: resolved.filterQuery }),
      resolved.filterQuery,
    );
    return _withTypedValueSlotSuggestions(ctx, directItems, valueSlots);
  }

  if (allowPositionalHints) {
    const concreteCommandTokens = (spec.flags || [])
      .filter(flag => {
        const value = String(flag.value || '');
        return value && !value.startsWith('-') && !value.startsWith('+');
      })
      .map(flag => autocompleteCore.buildItem({
        value: flag.value,
        description: flag.description || '',
        replaceStart: ctx.tokenStart,
        replaceEnd: ctx.tokenEnd,
        insertValue: flag.value,
      }));
    const matchingCommandTokens = autocompleteCore.filterItems(concreteCommandTokens, ctx.currentToken);
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
      .map(flag => autocompleteCore.buildItem({
        value: flag.value,
        description: flag.description || '',
        replaceStart: ctx.tokenStart,
        replaceEnd: ctx.tokenEnd,
        insertValue: flag.value,
      }));
    const filteredFlags = autocompleteCore.filterItems(flags, ctx.currentToken);
    if (!ctx.currentToken && ctx.atWhitespace && positionalHints.length && allowPositionalHints) {
      const resolved = _resolveAutocompleteHintSource(ctx, spec, positionalHints);
      const positionalItems = _hintsToItems(resolved.hints, ctx, { matchQuery: resolved.filterQuery });
      return _withTypedValueSlotSuggestions(
        ctx,
        filteredFlags.concat(positionalItems),
        valueSlots,
      );
    }
    return filteredFlags;
  }

  if (positionalHints.length && allowPositionalHints) {
    const resolved = _resolveAutocompleteHintSource(ctx, spec, positionalHints);
    const positionalItems = autocompleteCore.filterItems(
      _hintsToItems(resolved.hints, ctx, { matchQuery: resolved.filterQuery }),
      resolved.filterQuery,
    );
    return _withTypedValueSlotSuggestions(ctx, positionalItems, valueSlots);
  }
  const resolvedWorkspacePathHints = allowPositionalHints
    ? _resolveAutocompleteHintSource(ctx, spec, [], { allowWorkspaceTarget: false })
    : null;
  if (resolvedWorkspacePathHints && resolvedWorkspacePathHints.workspacePathActive) {
    const pathItems = autocompleteCore.filterItems(
      _hintsToItems(resolvedWorkspacePathHints.hints, ctx, { matchQuery: resolvedWorkspacePathHints.filterQuery }),
      resolvedWorkspacePathHints.filterQuery,
    );
    return _withTypedValueSlotSuggestions(ctx, pathItems, valueSlots);
  }
  return [];
}

function _buildPipeCommandAutocomplete(ctx, registry) {
  const items = Object.entries(registry)
    .filter(([, spec]) => spec && spec.pipe_command)
    .map(([root, spec]) => autocompleteCore.buildItem({
      value: spec.pipe_insert_value || root,
      label: spec.pipe_label || spec.pipe_insert_value || root,
      description: spec.pipe_description || '',
      replaceStart: ctx.tokenStart,
      replaceEnd: ctx.tokenEnd,
      insertValue: spec.pipe_insert_value || root,
    }));
  return autocompleteCore.filterItems(items, ctx.currentToken);
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
  return autocompleteCore.filterItems(((typeof acSuggestions !== 'undefined' && acSuggestions) || []), q).slice(0, 24);
}

function getAutocompleteMatches(value, cursorPos) {
  if (_isAutocompleteBlockedByActiveRun()) return [];
  const text = String(value || '');
  const ctx = _autocompleteTokenContext(text, cursorPos);
  const pipeCtx = _autocompletePipeContext(text, cursorPos);
  const runtimeItems = !pipeCtx && typeof getRuntimeAutocompleteItems === 'function'
    ? getRuntimeAutocompleteItems(ctx, autocompleteCore.buildItem, autocompleteCore.filterItems)
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
      && autocompleteCore.itemInsertValue(singleItem).toLowerCase() === ctx.currentToken.toLowerCase()) {
    return [];
  }
  return items;
}

function limitAutocompleteMatchesForDisplay(items, maxItems = 12) {
  return autocompleteCore.limitItemsForDisplay(items, maxItems);
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

function acIsHintOnly(item) {
  return !!(item && typeof item === 'object' && item.hintOnly);
}

function acSelectableItems(items) {
  return (Array.isArray(items) ? items : []).filter(item => !acIsHintOnly(item));
}

function acSelectableIndexes(items) {
  return (Array.isArray(items) ? items : [])
    .map((item, index) => (acIsHintOnly(item) ? -1 : index))
    .filter(index => index >= 0);
}

function acFirstSelectableIndex(items) {
  const indexes = acSelectableIndexes(items);
  return indexes.length ? indexes[0] : -1;
}

function acLastSelectableIndex(items) {
  const indexes = acSelectableIndexes(items);
  return indexes.length ? indexes[indexes.length - 1] : -1;
}

function acNextSelectableIndex(items, currentIndex, direction = 1) {
  const indexes = acSelectableIndexes(items);
  if (!indexes.length) return -1;
  const currentPos = indexes.indexOf(currentIndex);
  if (currentPos < 0) return direction < 0 ? indexes[indexes.length - 1] : indexes[0];
  const nextPos = direction < 0
    ? (currentPos <= 0 ? indexes.length - 1 : currentPos - 1)
    : ((currentPos + 1) % indexes.length);
  return indexes[nextPos];
}

function acShow(items) {
  if (_isAutocompleteBlockedByTerminalConfirm() || _isAutocompleteBlockedByActiveRun()) {
    acHide();
    return;
  }
  acDropdown.innerHTML = '';
  if (!items.length) { hideAcDropdown(); return; }
  _positionAutocomplete(items.length);
  if (acIndex >= items.length) acIndex = acLastSelectableIndex(items);
  if (acIndex >= 0 && acIsHintOnly(items[acIndex])) acIndex = acFirstSelectableIndex(items);
  const currentValue = (typeof getComposerValue === 'function')
    ? getComposerValue()
    : cmdInput.value;
  const currentCursor = (typeof getComposerState === 'function')
    ? getComposerState().selectionStart
    : (cmdInput && typeof cmdInput.selectionStart === 'number' ? cmdInput.selectionStart : currentValue.length);
  const tokenCtx = _autocompleteTokenContext(currentValue, currentCursor);
  const matchValue = (items.length && typeof items[0] === 'object') ? tokenCtx.currentToken : currentValue;
  const maxExampleLabelLen = items.reduce((max, s) =>
    (s && s.isExample ? Math.max(max, autocompleteCore.itemText(s).length) : max), 0);
  let hasRenderedConcrete = false;
  let hasRenderedHint = false;
  items.forEach((s, i) => {
    const hintOnly = acIsHintOnly(s);
    const hintSeparated = hintOnly && hasRenderedConcrete && !hasRenderedHint;
    const div = document.createElement('div');
    div.className = 'ac-item dropdown-item dropdown-item-dense'
      + (!hintOnly && i === acIndex ? ' ac-active dropdown-item-active' : '')
      + (s && s.isExample ? ' ac-example' : '')
      + (hintOnly ? ' ac-hint-only' : '')
      + (hintSeparated ? ' ac-hint-separated' : '');
    if (hintOnly) div.setAttribute('aria-disabled', 'true');
    const label = autocompleteCore.itemText(s);
    const description = autocompleteCore.itemDescription(s);
    const val = s && typeof s === 'object' && s.matchQuery != null
      ? String(s.matchQuery || '')
      : String(matchValue || '');
    const main = document.createElement('span');
    main.className = 'ac-item-main';
    if (s && s.isExample && maxExampleLabelLen > 0) main.style.minWidth = maxExampleLabelLen + 'ch';
    main.innerHTML = hintOnly
      ? escapeHtml(label)
      : autocompleteCore.highlightedLabel(label, val);
    div.appendChild(main);
    if (description) {
      const desc = document.createElement('span');
      desc.className = 'ac-item-desc';
      desc.textContent = description;
      div.appendChild(desc);
    }
    div.addEventListener('mousedown', e => {
      e.preventDefault();
      if (!hintOnly) acAccept(s);
    });
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
      if (dx < 10 && dy < 10) {
        e.preventDefault();
        if (!hintOnly) acAccept(s);
      }
    }, { passive: false });
    acDropdown.appendChild(div);
    if (hintOnly) hasRenderedHint = true;
    else hasRenderedConcrete = true;
  });
  showAcDropdown();
  _positionAutocomplete(items.length);
  _scrollAutocompleteActiveItem();
}

function acHide() {
  hideAcDropdown();
  acIndex = -1;
  if (typeof acFiltered !== 'undefined' && Array.isArray(acFiltered)) acFiltered = [];
}

function acExpandSharedPrefix(items) {
  if (!Array.isArray(items) || items.length < 2) return false;
  const currentValue = (typeof getComposerValue === 'function')
    ? getComposerValue()
    : (cmdInput ? cmdInput.value || '' : '');
  const firstItem = items[0];
  const sharedPrefix = autocompleteCore.sharedPrefix(items);
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

function _scheduleAutocompleteRefreshAfterAccept(insertValue) {
  if (!String(insertValue || '').endsWith('/')) return;
  setTimeout(() => {
    if (typeof openAutocompleteForVisibleComposer === 'function' && openAutocompleteForVisibleComposer()) return;
    const input = typeof getVisibleComposerInput === 'function' ? getVisibleComposerInput() : cmdInput;
    if (input && typeof input.dispatchEvent === 'function') {
      input.dispatchEvent(new Event('input'));
    }
  }, 0);
}

function acAccept(s) {
  let acceptedInsertValue = '';
  if (_isAutocompleteBlockedByTerminalConfirm()) {
    acHide();
    refocusComposerAfterAction({ preventScroll: true });
    return;
  }
  if (s && typeof s === 'object') {
    // Placeholder-only hints (e.g. "<token>") are display-only: Tab should hide
    // the dropdown, not insert the literal placeholder text into the prompt.
    if (s.hintOnly) {
      refocusComposerAfterAction({ preventScroll: true });
      return;
    }
    const currentValue = (typeof getComposerValue === 'function')
      ? getComposerValue()
      : (cmdInput ? cmdInput.value || '' : '');
    const insertValue = autocompleteCore.itemInsertText(s);
    acceptedInsertValue = insertValue;
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
    acceptedInsertValue = String(s || '');
    if (typeof acSuppressInputOnce !== 'undefined') acSuppressInputOnce = true;
    acHide();
    setComposerValue(s, s.length, s.length);
  }
  refocusComposerAfterAction({ preventScroll: true });
  _scheduleAutocompleteRefreshAfterAccept(acceptedInsertValue);
}
