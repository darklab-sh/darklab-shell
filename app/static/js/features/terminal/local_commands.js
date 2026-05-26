// ── Terminal-native theme/config commands ──
function _cliAppendLine(text, cls = '', tabId = null, metadata = null) {
  if (typeof appendLine === 'function') appendLine(text, cls, tabId, metadata);
}

function _cliShouldPreserveOutputTail(tabId = null) {
  const id = tabId || (typeof activeTabId !== 'undefined' ? activeTabId : null);
  const tab = typeof getTab === 'function' ? getTab(id) : null;
  return !!tab && tab.followOutput !== false;
}

function _cliPreserveOutputTail(tabId = null, shouldPreserve = true) {
  if (!shouldPreserve) return;
  const id = tabId || (typeof activeTabId !== 'undefined' ? activeTabId : null);
  const tab = typeof getTab === 'function' ? getTab(id) : null;
  const out = typeof getOutput === 'function' ? getOutput(id) : null;
  if (tab) tab.followOutput = true;
  if (out && typeof _stickOutputToBottom === 'function') {
    _stickOutputToBottom(out, tab);
  } else if (out) {
    out.scrollTop = out.scrollHeight;
  }
  if (typeof updateOutputFollowButton === 'function') updateOutputFollowButton(id);
}

function _cliSetStatus(statusValue) {
  if (typeof setStatus === 'function') setStatus(statusValue);
}

function _cliRecordSuccess(command) {
  if (typeof _recordSuccessfulLocalCommand === 'function') _recordSuccessfulLocalCommand(command);
}

function _cliThemeSlug(entry) {
  return _normalizeThemeName(entry?.name || entry?.filename || '');
}

function _cliThemeEntries() {
  return [..._getThemeThemes()].sort(_compareThemeEntries).filter(entry => _cliThemeSlug(entry));
}

function _cliThemeColorScheme(entry) {
  const scheme = String(entry?.color_scheme || '').trim().toLowerCase();
  if (scheme === 'light' || scheme === 'only light') return 'light';
  if (scheme === 'dark' || scheme === 'only dark') return 'dark';
  return 'other';
}

function _cliThemeColorSchemeLabel(scheme) {
  if (scheme === 'light') return 'Light themes:';
  if (scheme === 'dark') return 'Dark themes:';
  return 'Other themes:';
}

function _cliThemeEntriesByColorScheme() {
  const grouped = { dark: [], light: [], other: [] };
  _cliThemeEntries().forEach((entry) => {
    grouped[_cliThemeColorScheme(entry)].push(entry);
  });
  return grouped;
}

function _cliCurrentThemeEntry() {
  return _resolveThemeEntry(document.body?.dataset?.theme || _savedThemeName());
}

function _cliCurrentThemeSlug() {
  return _cliThemeSlug(_cliCurrentThemeEntry());
}

function _formatCliRecord(key, value, width = 18) {
  return `${key.padEnd(width)}  ${value}`;
}

function _cliThemeDescription(entry) {
  const label = String(entry?.label || entry?.name || '').trim();
  const slug = _cliThemeSlug(entry);
  const current = slug && slug === _cliCurrentThemeSlug();
  return `${label || slug}${current ? ' (current)' : ''}`;
}

async function handleThemeCommand(cmd, tabId = null) {
  const parts = String(cmd || '').trim().split(/\s+/).filter(Boolean);
  const sub = (parts[1] || '').toLowerCase();
  if (typeof appendCommandEcho === 'function') appendCommandEcho(cmd, tabId);

  if (parts.length === 1 || sub === 'list') {
    const current = _cliCurrentThemeEntry();
    _cliAppendLine(_formatCliRecord('current theme', _cliThemeDescription(current)), 'builtin-kv', tabId);
    _cliAppendLine('', 'builtin-spacer', tabId);
    _cliAppendLine('Available themes:', 'builtin-section', tabId);
    const grouped = _cliThemeEntriesByColorScheme();
    ['dark', 'light', 'other'].forEach((scheme) => {
      const entries = grouped[scheme] || [];
      if (!entries.length) return;
      _cliAppendLine(_cliThemeColorSchemeLabel(scheme), 'builtin-section', tabId);
      entries.forEach((entry) => {
        const slug = _cliThemeSlug(entry);
        const marker = slug === _cliCurrentThemeSlug() ? '*' : ' ';
        _cliAppendLine(`  ${marker} ${slug.padEnd(24)}  ${String(entry.label || slug)}`, 'builtin-help-row builtin-plain', tabId);
      });
    });
    _cliRecordSuccess(cmd);
    _cliSetStatus('ok');
    return true;
  }

  if (sub === 'current') {
    _cliAppendLine(_formatCliRecord('current theme', _cliThemeDescription(_cliCurrentThemeEntry())), 'builtin-kv', tabId);
    _cliRecordSuccess(cmd);
    _cliSetStatus('ok');
    return true;
  }

  const requested = sub === 'set' ? parts.slice(2).join(' ').trim() : '';
  if (!requested) {
    _cliAppendLine('usage: theme [list | current | set <theme>]', '', tabId);
    _cliSetStatus('fail');
    return true;
  }

  const entry = _findThemeEntry(requested);
  if (!entry) {
    _cliAppendLine(`theme: unknown theme '${requested}'`, 'exit-fail', tabId);
    _cliAppendLine("run 'theme list' to see available themes", '', tabId);
    _cliSetStatus('fail');
    return true;
  }

  applyThemeSelection(entry.name);
  _cliAppendLine(`theme set: ${_cliThemeDescription(entry)}`, '', tabId);
  _cliRecordSuccess(cmd);
  _cliSetStatus('ok');
  return true;
}

const _cliConfigValueLabels = {
  animated: 'animated',
  static: 'static',
  off: 'off',
  ask: 'ask',
};

function _cliNormalizeValue(value) {
  return String(value || '').trim().toLowerCase().replace(/_/g, '-');
}

function _cliNormalizePromptUsernameValue(value) {
  const raw = String(value || '').trim();
  const normalized = _cliNormalizeValue(raw);
  if (['default', 'clear', 'unset', 'server-default'].includes(normalized)) return '';
  return PreferenceCore.normalizePromptUsername(raw) || null;
}

function _cliConfigEntries() {
  return [
    {
      key: 'line-numbers',
      description: 'Show line numbers beside output and the live prompt',
      values: ['on', 'off'],
      get: () => (typeof lnMode === 'string' && lnMode === 'on' ? 'on' : 'off'),
      set: (value) => applyLineNumberPreference(value),
    },
    {
      key: 'timestamps',
      description: 'Timestamp display mode',
      values: _tsModes.slice(),
      get: () => (_tsModes.includes(tsMode) ? tsMode : 'off'),
      set: (value) => applyTimestampPreference(value),
    },
    {
      key: 'welcome',
      description: 'Welcome intro behavior',
      values: ['animated', 'static', 'off'],
      aliases: { disable_animation: 'static', disable: 'static', remove: 'off', removed: 'off' },
      toStored: { animated: 'animated', static: 'disable_animation', off: 'remove' },
      fromStored: { animated: 'animated', disable_animation: 'static', remove: 'off' },
      get: function getWelcomeCliValue() {
        return this.fromStored[getWelcomeIntroPreference()] || 'animated';
      },
      set: function setWelcomeCliValue(value) {
        applyWelcomeIntroPreference(this.toStored[value] || value);
      },
    },
    {
      key: 'share-redaction',
      description: 'Default redaction behavior for shared snapshots',
      values: ['ask', 'redacted', 'raw'],
      aliases: { unset: 'ask', prompt: 'ask', redacted: 'redacted', raw: 'raw' },
      toStored: { ask: 'unset', redacted: 'redacted', raw: 'raw' },
      fromStored: { unset: 'ask', redacted: 'redacted', raw: 'raw' },
      get: function getShareRedactionCliValue() {
        return this.fromStored[getShareRedactionDefaultPreference()] || 'ask';
      },
      set: function setShareRedactionCliValue(value) {
        applyShareRedactionDefaultPreference(this.toStored[value] || value);
      },
    },
    {
      key: 'project-auto-link-runs',
      description: 'Add completed external command runs to the active project',
      values: ['on', 'off'],
      get: () => getProjectAutoLinkExternalRunsPreference(),
      set: (value) => applyProjectAutoLinkExternalRunsPreference(value),
    },
    {
      key: 'project-auto-link-run-entities',
      description: 'Add generated Atlas entities when an auto-linked run is added to the active project',
      values: ['on', 'off'],
      get: () => getProjectAutoLinkRunEntitiesPreference(),
      set: (value) => applyProjectAutoLinkRunEntitiesPreference(value),
    },
    {
      key: 'run-notifications',
      description: 'Desktop notification when a run completes or is killed',
      values: ['on', 'off'],
      get: () => getRunNotifyPreference(),
      set: (value) => applyRunNotifyPreference(value),
    },
    {
      key: 'hud-clock',
      description: 'HUD clock timezone',
      values: _hudClockModes.slice(),
      get: () => getHudClockPreference(),
      set: (value) => applyHudClockPreference(value),
    },
    {
      key: 'compare-view',
      description: 'Default run comparison view',
      values: ['auto', 'side-by-side', 'unified', 'changes-only', 'findings-only'],
      aliases: {
        automatic: 'auto',
        responsive: 'auto',
        default: 'auto',
        split: 'side-by-side',
        sidebyside: 'side-by-side',
        changes: 'changes-only',
        findings: 'findings-only',
      },
      toStored: {
        auto: 'auto',
        'side-by-side': 'side_by_side',
        unified: 'unified',
        'changes-only': 'changes_only',
        'findings-only': 'findings_only',
      },
      fromStored: {
        auto: 'auto',
        side_by_side: 'side-by-side',
        unified: 'unified',
        changes_only: 'changes-only',
        findings_only: 'findings-only',
      },
      get: function getCompareViewCliValue() {
        return this.fromStored[getCompareViewModePreference()] || 'auto';
      },
      set: function setCompareViewCliValue(value) {
        applyCompareViewModePreference(this.toStored[value] || value);
      },
    },
    {
      key: 'compare-context',
      description: 'Default unchanged-line context in run comparison',
      values: ['3', '10', 'all'],
      aliases: { default: '3', minimal: '3', expanded: '10', full: 'all' },
      get: () => getCompareContextPreference(),
      set: (value) => applyCompareContextPreference(value),
    },
    {
      key: 'prompt-username',
      description: 'Username shown before the prompt domain',
      values: null,
      valueHelp: '<username> | default',
      get: () => getPromptUsernamePreference() || 'default',
      normalize: _cliNormalizePromptUsernameValue,
      set: (value) => applyPromptUsernamePreference(value),
    },
  ];
}

function _findCliConfigEntry(key) {
  const normalized = _cliNormalizeValue(key);
  return _cliConfigEntries().find(entry => entry.key === normalized) || null;
}

function _normalizeCliConfigEntryValue(entry, value) {
  if (typeof entry.normalize === 'function') {
    const normalized = entry.normalize(value);
    return normalized === '' || normalized ? normalized : null;
  }
  const normalized = _cliNormalizeValue(value);
  const aliased = entry.aliases && Object.prototype.hasOwnProperty.call(entry.aliases, normalized)
    ? entry.aliases[normalized]
    : normalized;
  return entry.values.includes(aliased) ? aliased : null;
}

function _cliConfigDisplayValue(value) {
  return _cliConfigValueLabels[value] || value;
}

function _printCliConfigEntry(entry, tabId) {
  _cliAppendLine(
    _formatCliRecord(entry.key, _cliConfigDisplayValue(entry.get()), 19),
    'builtin-kv',
    tabId,
  );
}

function _printCliConfigList(tabId) {
  _cliAppendLine('Current user config:', 'builtin-section', tabId);
  _cliConfigEntries().forEach(entry => _printCliConfigEntry(entry, tabId));
}

async function handleConfigCommand(cmd, tabId = null) {
  const parts = String(cmd || '').trim().split(/\s+/).filter(Boolean);
  const sub = (parts[1] || '').toLowerCase();
  const preserveTail = _cliShouldPreserveOutputTail(tabId);
  if (typeof appendCommandEcho === 'function') appendCommandEcho(cmd, tabId);

  if (parts.length === 1 || sub === 'list') {
    _printCliConfigList(tabId);
    _cliRecordSuccess(cmd);
    _cliSetStatus('ok');
    return true;
  }

  if (sub === 'get') {
    const key = parts[2] || '';
    const entry = _findCliConfigEntry(key);
    if (!entry) {
      _cliAppendLine(`config: unknown option '${key}'`, 'exit-fail', tabId);
      _cliAppendLine("run 'config list' to see available options", '', tabId);
      _cliSetStatus('fail');
      return true;
    }
    _printCliConfigEntry(entry, tabId);
    _cliRecordSuccess(cmd);
    _cliSetStatus('ok');
    return true;
  }

  const isSet = sub === 'set';
  const key = isSet ? parts[2] : '';
  const value = isSet ? parts[3] : '';
  const entry = _findCliConfigEntry(key);

  if (!entry || !value) {
    _cliAppendLine('usage: config [list | get <option> | set <option> <value>]', '', tabId);
    _cliSetStatus('fail');
    return true;
  }

  const normalizedValue = _normalizeCliConfigEntryValue(entry, value);
  if (normalizedValue === null) {
    _cliAppendLine(`config: invalid value '${value}' for ${entry.key}`, 'exit-fail', tabId);
    _cliAppendLine(`allowed values: ${entry.values ? entry.values.join(', ') : entry.valueHelp}`, '', tabId);
    _cliSetStatus('fail');
    return true;
  }

  await entry.set(normalizedValue);
  _cliAppendLine(`config set: ${entry.key}=${_cliConfigDisplayValue(entry.get())}`, '', tabId);
  _cliPreserveOutputTail(tabId, preserveTail);
  _cliRecordSuccess(cmd);
  _cliSetStatus('ok');
  return true;
}
