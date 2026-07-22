// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// ── Runner pure helpers ──────────────────────────────────────────────────
// Loaded before runner.js. DOM, stream, and tab orchestration stay in
// runner.js; small command/duration transforms live here so unit tests can
// target a supported browser-visible seam.
var DarklabRunnerCore = (function (global) {
  function formatElapsed(totalSecs) {
    if (totalSecs < 60) return totalSecs.toFixed(1) + 's';
    const h = Math.floor(totalSecs / 3600);
    const m = Math.floor((totalSecs % 3600) / 60);
    const s = (totalSecs % 60).toFixed(1);
    return h > 0 ? `${h}h ${m}m ${s}s` : `${m}m ${s}s`;
  }

  function _unquoteToken(token) {
    const value = String(token || '');
    if (value.length >= 2) {
      const first = value[0];
      if ((first === '"' || first === "'") && value[value.length - 1] === first) {
        return value.slice(1, -1);
      }
    }
    return value;
  }

  function _isQuotedToken(token) {
    const value = String(token || '');
    if (value.length < 2) return false;
    const first = value[0];
    return (first === '"' || first === "'") && value[value.length - 1] === first;
  }

  function _isValidOutputSinkPath(value) {
    const path = String(value || '');
    if (!path || path !== path.trim() || path.startsWith('/') || path.includes('\\')) return false;
    if ([...path].some(char => char.charCodeAt(0) < 32)) return false;
    const parts = path.split('/');
    return parts.length > 0 && parts.every(part => part && part !== '.' && part !== '..' && part.length <= 255);
  }

  function _parseStage(stageTokens) {
    if (!stageTokens.length) return null;
    const normalizedStageTokens = stageTokens.map(_unquoteToken);
    const helper = String(normalizedStageTokens[0]).toLowerCase();

    if (helper === 'grep') {
      let pattern = null;
      const options = { ignoreCase: false, invertMatch: false, extended: false };
      let index = 1;
      while (index < normalizedStageTokens.length) {
        const rawToken = stageTokens[index];
        const token = normalizedStageTokens[index];
        if (pattern !== null) return null;
        if (_isQuotedToken(rawToken)) {
          pattern = token;
          index += 1;
          continue;
        }
        if (token === '--') {
          if (index + 1 >= normalizedStageTokens.length) return null;
          pattern = normalizedStageTokens[index + 1];
          index += 2;
          continue;
        }
        if (token === '-e') {
          if (index + 1 >= normalizedStageTokens.length) return null;
          pattern = normalizedStageTokens[index + 1];
          index += 2;
          continue;
        }
        if (pattern === null && /^-[^-]/.test(token)) {
          for (const flag of token.slice(1)) {
            if (!['i', 'v', 'E'].includes(flag)) return null;
            if (flag === 'i') options.ignoreCase = true;
            if (flag === 'v') options.invertMatch = true;
            if (flag === 'E') options.extended = true;
          }
          index += 1;
          continue;
        }
        pattern = token;
        index += 1;
      }
      return pattern !== null ? { kind: 'grep', pattern, ...options } : null;
    }

    if (helper === 'head' || helper === 'tail') {
      if (normalizedStageTokens.length === 1) return { kind: helper, count: 10 };
      if (normalizedStageTokens.length === 2 && /^-\d+$/.test(normalizedStageTokens[1])) {
        return { kind: helper, count: Number(normalizedStageTokens[1].slice(1)) };
      }
      if (
        normalizedStageTokens.length !== 3
        || normalizedStageTokens[1] !== '-n'
        || !/^\d+$/.test(normalizedStageTokens[2])
      ) {
        return null;
      }
      return { kind: helper, count: Number(normalizedStageTokens[2]) };
    }

    if (helper === 'wc') {
      if (normalizedStageTokens.length === 2 && normalizedStageTokens[1] === '-l') {
        return { kind: 'wc_l' };
      }
      return null;
    }

    if (helper === 'sort') {
      if (normalizedStageTokens.length === 1) {
        return { kind: 'sort', reverse: false, numeric: false, unique: false };
      }
      if (normalizedStageTokens.length === 2) {
        const flag = normalizedStageTokens[1];
        if (/^-[rnu]+$/.test(flag) && new Set(flag.slice(1)).size === flag.length - 1) {
          const chars = new Set(flag.slice(1));
          if ([...chars].every(c => 'rnu'.includes(c))) {
            return {
              kind: 'sort',
              reverse: chars.has('r'),
              numeric: chars.has('n'),
              unique: chars.has('u'),
            };
          }
        }
      }
      return null;
    }

    if (helper === 'uniq') {
      if (normalizedStageTokens.length === 1) return { kind: 'uniq', count: false };
      if (normalizedStageTokens.length === 2 && normalizedStageTokens[1] === '-c') {
        return { kind: 'uniq', count: true };
      }
      return null;
    }

    if (helper === 'jq') {
      const options = { raw: false, compact: false };
      let expression = null;
      let index = 1;
      while (index < normalizedStageTokens.length) {
        const token = normalizedStageTokens[index];
        if (token === '-r' || token === '--raw-output') {
          options.raw = true;
          index += 1;
          continue;
        }
        if (token === '-c' || token === '--compact-output') {
          options.compact = true;
          index += 1;
          continue;
        }
        if (expression !== null) return null;
        expression = token;
        index += 1;
      }
      const selector = _parseJsonSelectorExpression(expression);
      return selector ? { kind: 'jq', selector, ...options } : null;
    }

    return null;
  }

  function _parseJsonSelectorExpression(expression) {
    const text = String(expression || '').trim();
    if (!text || text.length > 160) return null;
    if (/[`;{}$\\]/.test(text)) return null;

    const hasMatch = text.match(/^select\(has\("([A-Za-z_][A-Za-z0-9_-]*)"\)\)$/);
    if (hasMatch) return { op: 'filter_has', path: [hasMatch[1]] };

    const eqMatch = text.match(/^select\(\.([A-Za-z_][A-Za-z0-9_.-]*)\s*==\s*"([^"]{0,200})"\)$/);
    if (eqMatch) return { op: 'filter_eq', path: _jsonSelectorPath(eqMatch[1]), value: eqMatch[2] };

    const containsMatch = text.match(/^select\(\.([A-Za-z_][A-Za-z0-9_.-]*)\s+contains\s+"([^"]{0,200})"\)$/);
    if (containsMatch) return { op: 'filter_contains', path: _jsonSelectorPath(containsMatch[1]), value: containsMatch[2] };

    if (text === '.') return { op: 'identity' };
    if (text === '.[]') return { op: 'iterate', path: [] };

    const fieldMatch = text.match(/^\.([A-Za-z_][A-Za-z0-9_.-]*)(\[\])?$/);
    if (fieldMatch) {
      const path = _jsonSelectorPath(fieldMatch[1]);
      if (!path.length) return null;
      return fieldMatch[2] ? { op: 'iterate', path } : { op: 'field', path };
    }
    return null;
  }

  function _jsonSelectorPath(value) {
    return String(value || '').split('.').filter(Boolean);
  }

  function parseSyntheticPostFilterCommand(cmd) {
    if (!cmd || (!cmd.includes('|') && !cmd.includes('>'))) return false;
    if (cmd.includes('`') || cmd.includes('$(')) return null;
    if (/(^|\s)\d+>>?/.test(cmd)) return null;
    const tokens = [];
    const re = /"[^"]*"|'[^']*'|&&|\|\|?|;;?|>>?|<|[^\s|&;<>]+/g;
    let match = re.exec(cmd);
    while (match) {
      tokens.push(match[0]);
      match = re.exec(cmd);
    }
    if (!tokens.length) return null;
    if (tokens.some(token => ['&&', '||', ';', ';;', '<', '&'].includes(token))) return null;
    let sink = null;
    const redirectIndexes = tokens
      .map((token, index) => (['>', '>>'].includes(token) ? index : -1))
      .filter(index => index !== -1);
    if (redirectIndexes.length) {
      const redirectIndex = redirectIndexes[0];
      if (redirectIndexes.length !== 1 || redirectIndex <= 0 || redirectIndex !== tokens.length - 2) return null;
      const path = _unquoteToken(tokens[tokens.length - 1]).trim();
      if (!_isValidOutputSinkPath(path)) return null;
      sink = { kind: tokens[redirectIndex] === '>>' ? 'append' : 'redirect', path };
      tokens.splice(redirectIndex);
    }
    const pipeIndexes = tokens
      .map((token, index) => (token === '|' ? index : -1))
      .filter(index => index !== -1);
    if ((!pipeIndexes.length && !sink) || (pipeIndexes.length && pipeIndexes[0] <= 0)) return null;

    const stages = [];
    if (pipeIndexes.length) {
      let stageStart = pipeIndexes[0] + 1;
      const stageEnds = pipeIndexes.slice(1).concat(tokens.length);
      for (let index = 0; index < stageEnds.length; index += 1) {
        const pipeIndex = stageEnds[index];
        const stageTokens = tokens.slice(stageStart, pipeIndex);
        const helper = String(_unquoteToken(stageTokens[0] || '')).toLowerCase();
        if (helper === 'tee') {
          if (sink || index !== stageEnds.length - 1 || stageTokens.length !== 2) return null;
          const path = _unquoteToken(stageTokens[1]).trim();
          if (!_isValidOutputSinkPath(path)) return null;
          sink = { kind: 'tee', path };
          stageStart = pipeIndex + 1;
          continue;
        }
        const stage = _parseStage(stageTokens);
        if (!stage) return null;
        stages.push(stage);
        stageStart = pipeIndex + 1;
      }
    }

    return {
      kind: stages[0] ? stages[0].kind : (sink && sink.kind),
      baseCommand: tokens.slice(0, pipeIndexes.length ? pipeIndexes[0] : tokens.length).map(_unquoteToken).join(' '),
      stages,
      sink,
    };
  }

  function _syntheticPostFilterLineLimit(options) {
    const configured = options && options.maxOutputLines !== undefined
      ? options.maxOutputLines
      : global.APP_CONFIG && global.APP_CONFIG.max_output_lines;
    const limit = Number.parseInt(configured, 10);
    return Number.isFinite(limit) && limit > 0 ? limit : 0;
  }

  function applySyntheticPostFilterLines(lineItems, spec, options = {}) {
    const stages = spec && Array.isArray(spec.stages) ? spec.stages : [];
    let items = Array.isArray(lineItems) ? lineItems.slice() : [];
    const lineLimit = _syntheticPostFilterLineLimit(options);

    function textOf(item) {
      return String(item && item.text !== undefined ? item.text : item || '');
    }

    function plainItem(text) {
      return { text: String(text), cls: '' };
    }

    for (const stage of stages) {
      const kind = stage && stage.kind;
      if (kind === 'grep') {
        let matches;
        if (stage.extended) {
          let regex;
          try {
            regex = new RegExp(String(stage.pattern || ''), stage.ignoreCase ? 'i' : '');
          } catch (err) {
            return [{ text: `[error] Invalid synthetic grep regex: ${err.message}`, cls: 'exit-fail' }];
          }
          matches = (line) => regex.test(line);
        } else {
          const needle = String(stage.pattern || '');
          const normalizedNeedle = stage.ignoreCase ? needle.toLowerCase() : needle;
          matches = (line) => {
            const haystack = stage.ignoreCase ? line.toLowerCase() : line;
            return haystack.includes(normalizedNeedle);
          };
        }
        items = items.filter((item) => {
          const matched = matches(textOf(item));
          return stage.invertMatch ? !matched : matched;
        });
      } else if (kind === 'head') {
        items = items.slice(0, Math.max(0, Number(stage.count || 0)));
      } else if (kind === 'tail') {
        const count = Math.max(0, Number(stage.count || 0));
        items = count > 0 ? items.slice(-count) : [];
      } else if (kind === 'wc_l') {
        items = [plainItem(String(items.length))];
      } else if (kind === 'sort') {
        const numeric = !!stage.numeric;
        const sorted = items.slice().sort((a, b) => {
          const aText = textOf(a).trimStart();
          const bText = textOf(b).trimStart();
          if (numeric) {
            const aMatch = aText.match(/^[-+]?\d+\.?\d*/);
            const bMatch = bText.match(/^[-+]?\d+\.?\d*/);
            const aNum = aMatch ? Number(aMatch[0]) : Number.NEGATIVE_INFINITY;
            const bNum = bMatch ? Number(bMatch[0]) : Number.NEGATIVE_INFINITY;
            return aNum - bNum;
          }
          return aText.toLowerCase().localeCompare(bText.toLowerCase());
        });
        if (stage.reverse) sorted.reverse();
        items = sorted;
        if (stage.unique) {
          const seen = new Set();
          items = items.filter((item) => {
            const key = textOf(item);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
          });
        }
      } else if (kind === 'uniq') {
        const result = [];
        let previous = null;
        let count = 0;
        const flush = () => {
          if (previous === null) return;
          result.push(stage.count ? plainItem(`${String(count).padStart(7)} ${previous}`) : plainItem(previous));
        };
        items.forEach((item) => {
          const text = textOf(item);
          if (text === previous) {
            count += 1;
            return;
          }
          flush();
          previous = text;
          count = 1;
        });
        flush();
        items = result;
      } else if (kind === 'jq') {
        if (lineLimit && items.length > lineLimit) {
          return [{ text: '[error] jq input exceeded the buffered line safety cap', cls: 'exit-fail' }];
        }
        const result = _applyJsonSelectorStage(items, stage, plainItem, textOf);
        if (result.error) return [{ text: `[error] ${result.error}`, cls: 'exit-fail' }];
        items = result.items;
      }
    }
    return items;
  }

  function _applyJsonSelectorStage(items, stage, plainItem, textOf) {
    const parsed = _parseJsonInputItems(items, textOf);
    if (parsed.error) return parsed;
    const selected = [];
    for (const value of parsed.values) {
      const nextValues = _selectJsonValues(value, stage.selector);
      selected.push(...nextValues);
      if (selected.length > 1000) {
        return { error: 'jq output exceeded the 1000-line safety cap' };
      }
    }
    let totalChars = 0;
    const outputItems = [];
    for (const value of selected) {
      const text = _formatJsonSelectorValue(value, !!stage.raw, !!stage.compact);
      totalChars += text.length;
      if (totalChars > 200000) {
        return { error: 'jq output exceeded the 200 KB safety cap' };
      }
      for (const line of String(text).split('\n')) {
        outputItems.push(plainItem(line));
      }
    }
    return { items: outputItems };
  }

  function _parseJsonInputItems(items, textOf) {
    const lines = items.map(textOf).filter(line => String(line).trim() !== '');
    if (!lines.length) return { values: [] };
    const jsonlValues = [];
    let jsonlFailed = false;
    for (const line of lines) {
      try {
        jsonlValues.push(JSON.parse(line));
      } catch (_) {
        jsonlFailed = true;
        break;
      }
    }
    if (!jsonlFailed) return { values: jsonlValues };
    try {
      return { values: [JSON.parse(lines.join('\n'))] };
    } catch (_) {
      return { error: 'jq expected JSON or JSONL input' };
    }
  }

  function _selectJsonValues(value, selector) {
    if (!selector) return [];
    if (selector.op === 'identity') return [value];
    if (selector.op === 'field') return [_jsonPathValue(value, selector.path)].filter(item => item !== undefined);
    if (selector.op === 'iterate') {
      const target = selector.path.length ? _jsonPathValue(value, selector.path) : value;
      if (Array.isArray(target)) return target;
      return [];
    }
    if (selector.op === 'filter_has') {
      return _jsonPathValue(value, selector.path) !== undefined ? [value] : [];
    }
    if (selector.op === 'filter_eq') {
      return _jsonFilterText(_jsonPathValue(value, selector.path)) === String(selector.value) ? [value] : [];
    }
    if (selector.op === 'filter_contains') {
      return _jsonFilterText(_jsonPathValue(value, selector.path)).includes(String(selector.value)) ? [value] : [];
    }
    return [];
  }

  function _jsonFilterText(value) {
    if (value === undefined) return '';
    if (value === null) return 'null';
    if (['string', 'number', 'boolean'].includes(typeof value)) return String(value);
    return JSON.stringify(value);
  }

  function _jsonPathValue(value, path) {
    let current = value;
    for (const part of path || []) {
      if (!current || typeof current !== 'object' || Array.isArray(current)) return undefined;
      if (!Object.prototype.hasOwnProperty.call(current, part)) return undefined;
      current = current[part];
    }
    return current;
  }

  function _formatJsonSelectorValue(value, raw, compact) {
    if (raw && (value === null || ['string', 'number', 'boolean'].includes(typeof value))) {
      return value === null ? 'null' : String(value);
    }
    return compact ? JSON.stringify(value) : JSON.stringify(value, null, 2);
  }

  function isSyntheticPostFilterCommand(cmd) {
    return !!parseSyntheticPostFilterCommand(cmd);
  }

  function isSyntheticSortCommand(cmd) {
    const parsed = parseSyntheticPostFilterCommand(cmd);
    return !!(parsed && parsed.kind === 'sort');
  }

  function isSyntheticUniqCommand(cmd) {
    const parsed = parseSyntheticPostFilterCommand(cmd);
    return !!(parsed && parsed.kind === 'uniq');
  }

  function isSyntheticGrepCommand(cmd) {
    const parsed = parseSyntheticPostFilterCommand(cmd);
    return !!(parsed && parsed.kind === 'grep');
  }

  function isSyntheticHeadCommand(cmd) {
    const parsed = parseSyntheticPostFilterCommand(cmd);
    return !!(parsed && parsed.kind === 'head');
  }

  function isSyntheticTailCommand(cmd) {
    const parsed = parseSyntheticPostFilterCommand(cmd);
    return !!(parsed && parsed.kind === 'tail');
  }

  function isSyntheticWcLineCountCommand(cmd) {
    const parsed = parseSyntheticPostFilterCommand(cmd);
    return !!(parsed && parsed.kind === 'wc_l');
  }

  function isSyntheticJqCommand(cmd) {
    const parsed = parseSyntheticPostFilterCommand(cmd);
    return !!(parsed && parsed.kind === 'jq');
  }

  const api = Object.freeze({
    formatElapsed,
    parseSyntheticPostFilterCommand,
    applySyntheticPostFilterLines,
    isSyntheticPostFilterCommand,
    isSyntheticSortCommand,
    isSyntheticUniqCommand,
    isSyntheticGrepCommand,
    isSyntheticHeadCommand,
    isSyntheticTailCommand,
    isSyntheticWcLineCountCommand,
    isSyntheticJqCommand,
  });
  return api;
})(typeof window !== 'undefined' ? window : globalThis);

export const { applySyntheticPostFilterLines, formatElapsed, isSyntheticGrepCommand, isSyntheticHeadCommand, isSyntheticJqCommand, isSyntheticPostFilterCommand, isSyntheticSortCommand, isSyntheticTailCommand, isSyntheticUniqCommand, isSyntheticWcLineCountCommand, parseSyntheticPostFilterCommand } = DarklabRunnerCore;
export { DarklabRunnerCore };
