// ── Shared autocomplete logic ──

function _acItemText(item) {
  if (item && typeof item === 'object') {
    return String(item.label || item.value || '').trim();
  }
  return String(item || '').trim();
}

function _acItemInsertValue(item) {
  if (item && typeof item === 'object') {
    return String(item.insertValue || item.value || item.label || '').trim();
  }
  return String(item || '').trim();
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
  const pipeIndex = text.indexOf('|');
  if (pipeIndex < 0 || cursor <= pipeIndex) return null;
  if (text.indexOf('|', pipeIndex + 1) !== -1) return null;

  const baseCommand = text.slice(0, pipeIndex).trim();
  if (!baseCommand) return null;

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

function _buildAutocompleteItem({ value, description = '', replaceStart, replaceEnd, insertValue = null, label = null }) {
  return {
    value,
    label: label || value,
    description,
    replaceStart,
    replaceEnd,
    insertValue: insertValue || value,
  };
}

function _filterAutocompleteItems(items, query) {
  const q = String(query || '').toLowerCase();
  if (!q) return items.slice();
  return items.filter(item => _acItemInsertValue(item).toLowerCase().startsWith(q));
}

function _buildContextAutocomplete(ctx) {
  const registry = (typeof acContextRegistry !== 'undefined' && acContextRegistry) || {};
  const spec = ctx.commandRoot ? registry[ctx.commandRoot] : null;

  if (!spec) {
    // Unknown command root — suggest matching command roots from the registry
    // while the user is still typing the first token (no trailing space yet).
    if (ctx.tokens.length <= 1 && !ctx.atWhitespace && ctx.commandRoot) {
      const q = ctx.commandRoot.toLowerCase();
      const matchingRoots = Object.keys(registry).filter(root => root.toLowerCase().startsWith(q));
      // If exactly one command matches and it has examples, show those directly
      // so the user sees full invocation patterns while still typing the root.
      if (matchingRoots.length === 1) {
        const matchedSpec = registry[matchingRoots[0]];
        if (matchedSpec && matchedSpec.examples && matchedSpec.examples.length) {
          return _filterAutocompleteItems(
            matchedSpec.examples.map(ex => Object.assign(_buildAutocompleteItem({
              value: ex.value,
              description: ex.description || '',
              replaceStart: ctx.tokenStart,
              replaceEnd: ctx.tokenEnd,
              insertValue: ex.value,
            }), { isExample: true })),
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
  if (spec.examples && spec.examples.length && ctx.tokens.length === 1 && !ctx.atWhitespace) {
    return _filterAutocompleteItems(
      spec.examples.map(ex => Object.assign(_buildAutocompleteItem({
        value: ex.value,
        description: ex.description || '',
        replaceStart: ctx.tokenStart,
        replaceEnd: ctx.tokenEnd,
        insertValue: ex.value,
      }), { isExample: true })),
      ctx.currentToken,
    );
  }

  const currentIsFlag = ctx.currentToken.startsWith('-') || ctx.currentToken.startsWith('+');
  const expectsValue = Array.isArray(spec.expects_value) ? spec.expects_value : [];
  const argHints = spec.arg_hints || {};
  const previousLower = String(ctx.previousToken || '').toLowerCase();

  const directHints = Object.prototype.hasOwnProperty.call(argHints, ctx.previousToken || '')
    ? argHints[ctx.previousToken || '']
    : (Object.prototype.hasOwnProperty.call(argHints, previousLower) ? argHints[previousLower] : null);
  if (directHints !== null) {
    return _filterAutocompleteItems(
      directHints.map(item => _buildAutocompleteItem({
        value: item.value,
        description: item.description || '',
        replaceStart: ctx.tokenStart,
        replaceEnd: ctx.tokenEnd,
      })),
      ctx.currentToken,
    );
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
    if (!ctx.currentToken && ctx.atWhitespace && positionalHints.length) {
      const positionalItems = positionalHints.map(item => _buildAutocompleteItem({
        value: item.value,
        label: item.label || item.value,
        description: item.description || '',
        replaceStart: ctx.tokenStart,
        replaceEnd: ctx.tokenEnd,
        insertValue: item.insertValue || item.value,
      }));
      return filteredFlags.concat(positionalItems);
    }
    return filteredFlags;
  }

  if (positionalHints.length) {
    return _filterAutocompleteItems(
      positionalHints.map(item => _buildAutocompleteItem({
        value: item.value,
        label: item.label || item.value,
        description: item.description || '',
        replaceStart: ctx.tokenStart,
        replaceEnd: ctx.tokenEnd,
        insertValue: item.insertValue || item.value,
      })),
      ctx.currentToken,
    );
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
  const registry = (typeof acContextRegistry !== 'undefined' && acContextRegistry) || {};
  if (!ctx.commandRoot) return _buildPipeCommandAutocomplete(ctx, registry);

  const spec = registry[ctx.commandRoot];
  if (!spec || !spec.pipe_command) return [];
  return _buildContextAutocomplete(ctx);
}

function _buildFlatAutocomplete(value) {
  const q = String(value || '').trim().toLowerCase();
  if (!q) return [];
  return ((typeof acSuggestions !== 'undefined' && acSuggestions) || [])
    .filter(s => String(s || '').toLowerCase().startsWith(q))
    .slice(0, 24);
}

function getAutocompleteMatches(value, cursorPos) {
  const text = String(value || '');
  const ctx = _autocompleteTokenContext(text, cursorPos);
  const pipeCtx = _autocompletePipeContext(text, cursorPos);
  let items = pipeCtx ? _buildPipeAutocomplete(pipeCtx) : _buildContextAutocomplete(ctx);
  if (!items.length && !pipeCtx) items = _buildFlatAutocomplete(text);

  if (!items.length) return [];
  if (typeof items[0] === 'string') {
    const q = text.trim().toLowerCase();
    if (items.some(item => String(item).toLowerCase() === q)) return [];
    return items;
  }

  if (items.length === 1 && _acItemInsertValue(items[0]).toLowerCase() === ctx.currentToken.toLowerCase()) {
    return [];
  }
  return items;
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
  const available = showAbove ? spaceAbove : spaceBelow;
  const edgeBuffer = mobileComposerMode ? 12 : (showAbove ? 20 : 30);
  const maxHeight = Math.max(0, Math.min(mobileComposerMode ? 200 : 260, available > edgeBuffer ? available - edgeBuffer : available));
  const visibleHeight = Math.max(0, Math.min(targetHeight, maxHeight || targetHeight));
  acDropdown.style.maxHeight = `${Math.round(maxHeight)}px`;
  acDropdown.style.top = showAbove
    ? `${Math.max(8, Math.round(rect.top - visibleHeight - 2))}px`
    : `${Math.max(8, Math.round(rect.bottom + 2))}px`;
  acDropdown.style.bottom = 'auto';
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
    div.className = 'ac-item' + (i === acIndex ? ' ac-active' : '') + (s && s.isExample ? ' ac-example' : '');
    const label = _acItemText(s);
    const description = _acItemDescription(s);
    const val = String(matchValue || '');
    const idx = val ? label.toLowerCase().indexOf(val.toLowerCase()) : -1;
    const main = document.createElement('span');
    main.className = 'ac-item-main';
    if (s && s.isExample && maxExampleLabelLen > 0) main.style.minWidth = maxExampleLabelLen + 'ch';
    if (idx >= 0 && val) {
      main.innerHTML = escapeHtml(label.slice(0, idx))
        + '<span class="ac-match">' + escapeHtml(label.slice(idx, idx + val.length)) + '</span>'
        + escapeHtml(label.slice(idx + val.length));
    } else {
      main.textContent = label;
    }
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
  if (s && typeof s === 'object') {
    const currentValue = (typeof getComposerValue === 'function')
      ? getComposerValue()
      : (cmdInput ? cmdInput.value || '' : '');
    const insertValue = _acItemInsertValue(s);
    const replaceStart = Number(s.replaceStart);
    const replaceEnd = Number(s.replaceEnd);
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
    acHide();
    setComposerValue(s, s.length, s.length);
  }
  if (typeof focusAnyComposerInput === 'function' && focusAnyComposerInput({ preventScroll: true })) return;
}
