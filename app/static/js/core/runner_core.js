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

  function _parseStage(stageTokens) {
    if (!stageTokens.length) return null;
    const normalizedStageTokens = stageTokens.map(_unquoteToken);
    const helper = String(normalizedStageTokens[0]).toLowerCase();

    if (helper === 'grep') {
      let pattern = null;
      const options = { ignoreCase: false, invertMatch: false, extended: false };
      for (const token of normalizedStageTokens.slice(1)) {
        if (pattern === null && /^-[^-]/.test(token)) {
          for (const flag of token.slice(1)) {
            if (!['i', 'v', 'E'].includes(flag)) return null;
            if (flag === 'i') options.ignoreCase = true;
            if (flag === 'v') options.invertMatch = true;
            if (flag === 'E') options.extended = true;
          }
          continue;
        }
        if (pattern !== null) return null;
        pattern = token;
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

    return null;
  }

  function parseSyntheticPostFilterCommand(cmd) {
    if (!cmd || !cmd.includes('|')) return false;
    if (cmd.includes('`') || cmd.includes('$(')) return null;
    const tokens = [];
    const re = /"[^"]*"|'[^']*'|&&|\|\|?|;;?|>>?|<|[^\s|&;<>]+/g;
    let match = re.exec(cmd);
    while (match) {
      tokens.push(match[0]);
      match = re.exec(cmd);
    }
    if (!tokens.length) return null;
    if (tokens.some(token => ['&&', '||', ';', ';;', '>', '>>', '<', '&'].includes(token))) return null;
    const pipeIndexes = tokens
      .map((token, index) => (token === '|' ? index : -1))
      .filter(index => index !== -1);
    if (!pipeIndexes.length || pipeIndexes[0] <= 0) return null;

    const stages = [];
    let stageStart = pipeIndexes[0] + 1;
    for (const pipeIndex of pipeIndexes.slice(1).concat(tokens.length)) {
      const stageTokens = tokens.slice(stageStart, pipeIndex);
      const stage = _parseStage(stageTokens);
      if (!stage) return null;
      stages.push(stage);
      stageStart = pipeIndex + 1;
    }

    return {
      kind: stages[0] ? stages[0].kind : null,
      baseCommand: tokens.slice(0, pipeIndexes[0]).map(_unquoteToken).join(' '),
      stages,
    };
  }

  function applySyntheticPostFilterLines(lineItems, spec) {
    const stages = spec && Array.isArray(spec.stages) ? spec.stages : [];
    let items = Array.isArray(lineItems) ? lineItems.slice() : [];

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
      }
    }
    return items;
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
  });
  global.DarklabRunnerCore = api;
  return api;
})(typeof window !== 'undefined' ? window : globalThis);
