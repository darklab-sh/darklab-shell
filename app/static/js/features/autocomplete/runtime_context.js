// Runtime autocomplete contexts for built-ins, workspace paths, variables, and command lookup.

function _runtimeHint(value, description = '', insertValue = null, label = null, hintOnly = null) {
  const item = { value, description };
  if (insertValue != null) item.insertValue = insertValue;
  if (label != null) item.label = label;
  if (hintOnly != null) item.hintOnly = !!hintOnly;
  return item;
}

function _runtimePlaceholderHint(value, description = '') {
  return _runtimeHint(value, description, null, null, true);
}

function _runtimeContextSpec({
  flags = [],
  expectsValue = [],
  argHints = {},
  sequenceArgHints = {},
  workspacePathArgKinds = {},
  argumentLimit = null,
  pipeCommand = false,
  pipeInsertValue = '',
  pipeLabel = '',
  pipeDescription = '',
  examples = [],
  closeAfter = {},
} = {}) {
  return {
    flags,
    expects_value: expectsValue,
    arg_hints: argHints,
    sequence_arg_hints: sequenceArgHints,
    workspace_path_arg_kinds: workspacePathArgKinds,
    argument_limit: argumentLimit,
    pipe_command: pipeCommand,
    pipe_insert_value: pipeInsertValue,
    pipe_label: pipeLabel,
    pipe_description: pipeDescription,
    examples,
    close_after: closeAfter,
  };
}

function isWorkspaceFeatureEnabled() {
  return !!(typeof APP_CONFIG !== 'undefined' && APP_CONFIG && APP_CONFIG.workspace_enabled === true);
}

function isTourFeatureEnabled() {
  return !(typeof APP_CONFIG !== 'undefined' && APP_CONFIG) || APP_CONFIG.tour_enabled === true;
}

function _runtimeSpecEnabledForFeatures(root, spec) {
  const featureRequired = spec && spec.feature_required;
  const features = Array.isArray(featureRequired) ? featureRequired : [featureRequired];
  if (features.some(feature => String(feature || '').toLowerCase() === 'workspace')) {
    return isWorkspaceFeatureEnabled();
  }
  if (features.some(feature => String(feature || '').toLowerCase() === 'tour')) {
    return isTourFeatureEnabled();
  }
  return !['file', 'cat', 'ls', 'rm'].includes(String(root || '').toLowerCase()) || isWorkspaceFeatureEnabled();
}

function _cloneRuntimeSpec(spec) {
  if (!spec || typeof spec !== 'object') return _runtimeContextSpec();
  try {
    return JSON.parse(JSON.stringify(spec));
  } catch (err) {
    return _runtimeContextSpec();
  }
}

function _runtimeMergeHints(baseHints = {}, overlayHints = {}) {
  const merged = Object.assign({}, baseHints || {});
  Object.entries(overlayHints || {}).forEach(([trigger, hints]) => {
    const bucket = Array.isArray(merged[trigger]) ? merged[trigger].slice() : [];
    const seen = new Set(bucket.map(item => String(item && item.value || '').toLowerCase()));
    const seenInserts = new Map();
    bucket.forEach((item, index) => {
      const insertValue = String(item && item.insertValue || '').toLowerCase();
      if (insertValue && !seenInserts.has(insertValue)) seenInserts.set(insertValue, index);
    });
    (hints || []).forEach((hint) => {
      const value = String(hint && hint.value || '');
      const key = value.toLowerCase();
      const insertValue = String(hint && hint.insertValue || '').toLowerCase();
      if (!value || seen.has(key)) return;
      if (insertValue && seenInserts.has(insertValue)) {
        const existingIndex = seenInserts.get(insertValue);
        const existing = bucket[existingIndex];
        const existingKey = String(existing && existing.value || '').toLowerCase();
        seen.delete(existingKey);
        seen.add(key);
        bucket[existingIndex] = hint;
        return;
      }
      seen.add(key);
      if (insertValue) seenInserts.set(insertValue, bucket.length);
      bucket.push(hint);
    });
    merged[trigger] = bucket;
  });
  return merged;
}

function _runtimeMergeContextSpec(baseSpec = {}, overlaySpec = {}) {
  const merged = _cloneRuntimeSpec(baseSpec);
  const appendItems = (key) => {
    const bucket = Array.isArray(merged[key]) ? merged[key] : [];
    const seen = new Set(bucket.map(item => String(item && item.value != null ? item.value : item).toLowerCase()));
    (overlaySpec[key] || []).forEach((item) => {
      const raw = item && item.value != null ? item.value : item;
      const value = String(raw || '');
      const lookup = value.toLowerCase();
      if (!value || seen.has(lookup)) return;
      seen.add(lookup);
      bucket.push(item);
    });
    merged[key] = bucket;
  };
  appendItems('flags');
  appendItems('expects_value');
  appendItems('examples');
  merged.arg_hints = _runtimeMergeHints(merged.arg_hints, overlaySpec.arg_hints);
  merged.sequence_arg_hints = _runtimeMergeHints(merged.sequence_arg_hints, overlaySpec.sequence_arg_hints);
  merged.workspace_path_arg_kinds = Object.assign(
    {},
    merged.workspace_path_arg_kinds || {},
    overlaySpec.workspace_path_arg_kinds || {},
  );
  merged.close_after = Object.assign({}, merged.close_after || {}, overlaySpec.close_after || {});
  if (Number.isInteger(overlaySpec.argument_limit) && overlaySpec.argument_limit > 0) {
    merged.argument_limit = overlaySpec.argument_limit;
  }
  return merged;
}

function _runtimeActiveBuiltinRoots(baseRegistry = {}) {
  const roots = new Set(
    Array.isArray(acBuiltinCommandRoots) ? acBuiltinCommandRoots.map(root => String(root || '')) : [],
  );
  Object.entries(baseRegistry || {}).forEach(([root, spec]) => {
    if (spec && typeof spec === 'object' && String(spec.description || '').startsWith('built-in:')) {
      roots.add(root);
    }
  });
  return [...roots].filter(Boolean).sort();
}

function _runtimeBuiltinDescription(root, baseRegistry = {}) {
  return String(baseRegistry[root]?.description || 'built-in command');
}

function _runtimeAllowedCommandRoots() {
  const roots = new Set();
  const source = allowedCommandsFaqData && Array.isArray(allowedCommandsFaqData.commands)
    ? allowedCommandsFaqData.commands
    : [];
  source.forEach((command) => {
    const root = String(command || '').trim().split(/\s+/, 1)[0].toLowerCase();
    if (root) roots.add(root);
  });
  return roots;
}

function _runtimeCommandLookupHints(baseRegistry = {}, descriptionForExternal = 'manual page') {
  const builtinNames = new Set(
    _runtimeActiveBuiltinRoots(baseRegistry)
      .filter(root => _runtimeSpecEnabledForFeatures(root, baseRegistry[root])),
  );
  const externalRoots = new Set(
    Object.keys(baseRegistry || {})
      .filter(root => _runtimeSpecEnabledForFeatures(root, baseRegistry[root])),
  );
  _runtimeAllowedCommandRoots().forEach(root => externalRoots.add(root));
  builtinNames.forEach(root => externalRoots.delete(root));

  const items = [];
  [...externalRoots].sort().forEach(root => {
    items.push(_runtimeHint(root, `${root} ${descriptionForExternal}`));
  });
  [...builtinNames].sort().forEach(root => {
    items.push(_runtimeHint(root, _runtimeBuiltinDescription(root, baseRegistry)));
  });
  items.push(_runtimePlaceholderHint('<command>', 'Any built-in or allowed command'));
  return items;
}

function _runtimeWorkspaceFileHints() {
  return _runtimeWorkspaceEntryHints('file');
}

function _runtimeWorkspaceDirectoryHints() {
  return _runtimeWorkspaceEntryHints('directory');
}

function _runtimeWorkspaceDirectoryNavigationHints() {
  return _runtimeWorkspaceDirectoryHints().map((hint) => {
    const value = String(hint && hint.value || '').trim();
    if (!value || value === '/' || value.endsWith('/')) return hint;
    return _runtimeHint(`${value}/`, hint.description || 'session folder');
  });
}

function _runtimeWorkspaceFilePathHints() {
  return _runtimeWorkspaceFileHints().concat(_runtimeWorkspaceDirectoryNavigationHints());
}

function _runtimeWorkspaceCwd() {
  if (typeof _workspaceCwd === 'function') return _workspaceCwd(activeTabId);
  if (typeof getTab === 'function') {
    const tab = getTab(activeTabId);
    const parts = String(tab && tab.workspaceCwd || '').split('/').filter(Boolean);
    return parts.join('/');
  }
  return '';
}

function _runtimeWorkspaceRelativeValue(path = '', cwd = '') {
  const normalizedPath = String(path || '').split('/').filter(Boolean).join('/');
  const normalizedCwd = String(cwd || '').split('/').filter(Boolean).join('/');
  if (!normalizedCwd) return normalizedPath;
  if (!normalizedPath.startsWith(`${normalizedCwd}/`)) return '';
  return normalizedPath.slice(normalizedCwd.length + 1);
}

function _runtimeWorkspaceDirectHintFromPath(item, cwd = '', kind = 'file') {
  const relative = _runtimeWorkspaceRelativeValue(item && item.value, cwd);
  if (!relative || relative.includes('/')) return null;
  const value = kind === 'directory' && relative !== '/' && !relative.endsWith('/')
    ? `${relative}/`
    : relative;
  return _runtimeHint(value, item && item.description || '');
}

function _runtimeNormalizeWorkspaceCommandPath(path = '', cwd = '') {
  if (typeof normalizeWorkspaceCommandPath === 'function') {
    return String(normalizeWorkspaceCommandPath(path, cwd) || '').split('/').filter(Boolean).join('/');
  }
  const raw = String(path ?? '').trim();
  const baseParts = raw.startsWith('/') ? [] : String(cwd || '').split('/').filter(Boolean);
  raw.split('/').forEach((part) => {
    const trimmed = String(part || '').trim();
    if (!trimmed || trimmed === '.') return;
    if (trimmed === '..') {
      if (!baseParts.length) throw new Error('path escapes the session workspace');
      baseParts.pop();
      return;
    }
    if (trimmed.includes('\\') || trimmed.includes('\x00')) {
      throw new Error('file name contains unsupported characters');
    }
    baseParts.push(trimmed);
  });
  return baseParts.join('/');
}

function _runtimeWorkspaceCompletionParts(token = '') {
  const rawToken = String(token || '');
  const slashIndex = rawToken.lastIndexOf('/');
  if (slashIndex < 0) return null;
  const typedPrefix = rawToken.slice(0, slashIndex + 1);
  try {
    return {
      typedPrefix,
      resolvedDirectory: _runtimeNormalizeWorkspaceCommandPath(typedPrefix || '.', _runtimeWorkspaceCwd()),
    };
  } catch (_) {
    return null;
  }
}

function _runtimeWorkspaceAllHints(kind = 'file') {
  return kind === 'directory'
    ? (typeof getWorkspaceAutocompleteDirectoryHints === 'function' ? getWorkspaceAutocompleteDirectoryHints() : [])
    : (typeof getWorkspaceAutocompleteFileHints === 'function' ? getWorkspaceAutocompleteFileHints() : []);
}

function _runtimeWorkspaceHintDescription(path = '', kind = 'file') {
  const normalized = String(path || '').split('/').filter(Boolean).join('/');
  const allHints = _runtimeWorkspaceAllHints(kind);
  const existing = (Array.isArray(allHints) ? allHints : [])
    .find(item => String(item && item.value || '').split('/').filter(Boolean).join('/') === normalized);
  return existing && existing.description
    ? existing.description
    : (kind === 'directory' ? 'session folder' : 'session file');
}

function _runtimeWorkspaceCompletionKinds(kind = 'file') {
  const normalized = String(kind || 'file').toLowerCase();
  if (normalized === 'any') return ['file', 'directory'];
  if (normalized === 'directory') return ['directory'];
  return ['file', 'directory'];
}

function _runtimeWorkspaceEntryValue(parts, name, wantedKind) {
  const value = `${parts.typedPrefix}${name}`;
  return wantedKind === 'directory' ? `${value}/` : value;
}

function _runtimeWorkspaceScopedHints(kind = 'file', token = '') {
  const parts = _runtimeWorkspaceCompletionParts(token);
  if (!parts || typeof getWorkspaceDirectoryEntries !== 'function') return [];
  const entries = getWorkspaceDirectoryEntries(parts.resolvedDirectory) || {};
  const hints = [];
  _runtimeWorkspaceCompletionKinds(kind).forEach((wantedKind) => {
    const source = wantedKind === 'directory' ? entries.folders : entries.files;
    (Array.isArray(source) ? source : []).forEach((entry) => {
      const name = String(entry && entry.name || '').trim();
      const path = String(entry && entry.path || '').split('/').filter(Boolean).join('/');
      if (!name) return;
      hints.push(_runtimeHint(
        _runtimeWorkspaceEntryValue(parts, name, wantedKind),
        _runtimeWorkspaceHintDescription(path, wantedKind),
      ));
    });
  });
  return hints;
}

function _runtimeWorkspaceEntryHints(kind = 'file') {
  const cwd = _runtimeWorkspaceCwd();
  if (typeof getWorkspaceDirectoryEntries === 'function') {
    const entries = getWorkspaceDirectoryEntries(cwd) || {};
    const source = kind === 'directory' ? entries.folders : entries.files;
    const allHints = kind === 'directory'
      ? (typeof getWorkspaceAutocompleteDirectoryHints === 'function' ? getWorkspaceAutocompleteDirectoryHints() : [])
      : (typeof getWorkspaceAutocompleteFileHints === 'function' ? getWorkspaceAutocompleteFileHints() : []);
    return (Array.isArray(source) ? source : []).map((entry) => {
      const path = String(entry && entry.path || '').split('/').filter(Boolean).join('/');
      const name = String(entry && entry.name || _runtimeWorkspaceRelativeValue(path, cwd)).trim();
      const value = kind === 'directory' && name && name !== '/' && !name.endsWith('/')
        ? `${name}/`
        : name;
      const existing = allHints.find(item => String(item && item.value || '') === path);
      return value ? _runtimeHint(value, existing && existing.description || (kind === 'directory' ? 'session folder' : 'session file')) : null;
    }).filter(Boolean);
  }
  if (kind === 'directory') {
    if (typeof getWorkspaceAutocompleteDirectoryHints !== 'function') return [];
    return getWorkspaceAutocompleteDirectoryHints()
      .map(item => _runtimeWorkspaceDirectHintFromPath(item, cwd, 'directory'))
      .filter(Boolean);
  }
  if (typeof getWorkspaceAutocompleteFileHints !== 'function') return [];
  return getWorkspaceAutocompleteFileHints()
    .map(item => _runtimeWorkspaceDirectHintFromPath(item, cwd))
    .filter(Boolean);
}

function _runtimeWorkspaceMoveSourceHints() {
  return _runtimeWorkspaceFileHints().concat(_runtimeWorkspaceDirectoryHints());
}

function _runtimeWorkspaceMoveDestinationHints() {
  return _runtimeWorkspaceDirectoryHints().concat([_runtimeHint('/', 'Session workspace root')]);
}

function _runtimeWorkspaceMoveDestinationHintsForSource(source, destinationHints) {
  const sourcePath = String(source || '').trim();
  const normalizedSource = sourcePath.split('/').filter(Boolean).join('/');
  return (Array.isArray(destinationHints) ? destinationHints : []).filter((hint) => {
    const value = String(hint && hint.value || '').trim();
    const normalizedValue = value.split('/').filter(Boolean).join('/');
    return value === '/'
      || (normalizedValue && normalizedValue !== normalizedSource && !normalizedValue.startsWith(`${normalizedSource}/`));
  });
}

function _runtimeWorkspaceMoveSequenceHints(prefix, sourceHints, destinationHints) {
  const sequenceHints = {};
  (Array.isArray(sourceHints) ? sourceHints : []).forEach((hint) => {
    const value = String(hint && hint.value || '').trim().toLowerCase();
    if (!value) return;
    sequenceHints[`${prefix} ${value}`] = _runtimeWorkspaceMoveDestinationHintsForSource(value, destinationHints);
  });
  return sequenceHints;
}

function getWorkspaceAutocompletePathHints(kind = 'file', token = '') {
  return _runtimeWorkspaceScopedHints(kind, token);
}

function getWorkspaceAutocompleteFlagFileHints(token = '') {
  return String(token || '').includes('/')
    ? _runtimeWorkspaceScopedHints('file', token)
    : _runtimeWorkspaceFilePathHints();
}

function _runtimeWorkspaceContext() {
  const fileHints = _runtimeWorkspaceFileHints();
  const filePathHints = _runtimeWorkspaceFilePathHints();
  const directoryHints = _runtimeWorkspaceDirectoryHints();
  const deleteHints = fileHints.concat(directoryHints);
  const moveSourceHints = _runtimeWorkspaceMoveSourceHints();
  const moveDestinationHints = _runtimeWorkspaceMoveDestinationHints();
  return _runtimeContextSpec({
    expectsValue: ['show', 'add', 'add-dir', 'edit', 'download', 'move', 'rm', 'delete', 'ls'],
    argHints: {
      list: [_runtimeHint('-l', 'Long listing'), _runtimeHint('-R', 'Recursive listing')].concat(directoryHints, [_runtimeHint('/', 'Session workspace root')]),
      ls: [_runtimeHint('-l', 'Long listing'), _runtimeHint('-R', 'Recursive listing')].concat(directoryHints, [_runtimeHint('/', 'Session workspace root')]),
      help: [],
      show: filePathHints,
      add: [_runtimePlaceholderHint('<file>', 'New session file name')],
      'add-dir': directoryHints.concat([_runtimePlaceholderHint('<folder>', 'New session folder')]),
      edit: filePathHints,
      download: filePathHints,
      move: moveSourceHints,
      rm: [_runtimeHint('-r', 'Remove folders recursively'), _runtimeHint('-rf', 'Remove folders recursively')].concat(deleteHints),
      delete: [_runtimeHint('-r', 'Remove folders recursively'), _runtimeHint('-rf', 'Remove folders recursively')].concat(deleteHints),
      __positional__: [
        _runtimeHint('show <file>', 'Print a session file in the terminal', 'show '),
        _runtimeHint('add <file>', 'Open the Files editor for a new session file', 'add '),
        _runtimeHint('add-dir <folder>', 'Create a session folder', 'add-dir '),
        _runtimeHint('edit <file>', 'Open the Files editor for an existing session file', 'edit '),
        _runtimeHint('download <file>', 'Download a session file through the browser', 'download '),
        _runtimeHint('move <source> <destination>', 'Move or rename a session file or folder', 'move '),
        _runtimeHint('delete <file>', 'Remove a session file from this session', 'delete '),
        _runtimeHint('help', 'Show file command usage'),
      ],
    },
    sequenceArgHints: _runtimeWorkspaceMoveSequenceHints('move', moveSourceHints, moveDestinationHints),
    workspacePathArgKinds: {
      list: ['directory'],
      ls: ['directory'],
      show: ['file'],
      edit: ['file'],
      download: ['file'],
      move: ['any', 'directory'],
      rm: ['any'],
      delete: ['any'],
    },
  });
}

function _runtimeWorkspaceNavigableDirectoryHints() {
  const hints = _runtimeWorkspaceDirectoryHints();
  const cwd = _runtimeWorkspaceCwd();
  if (cwd) hints.unshift(_runtimeHint('../', 'Parent workspace folder'));
  hints.push(_runtimeHint('/', 'Session workspace root'));
  return hints;
}

function _runtimeThemeContext() {
  const themeHints = _cliThemeEntries().map(entry => _runtimeHint(_cliThemeSlug(entry), _cliThemeDescription(entry)));
  const argHints = {
    list: [],
    current: [],
    set: themeHints,
    __positional__: [
      _runtimeHint('list', 'Show available themes'),
      _runtimeHint('current', 'Show the active theme'),
      _runtimeHint('set', 'Apply a theme', 'set '),
    ],
  };
  themeHints.forEach(item => { argHints[item.value] = []; });
  return _runtimeContextSpec({ expectsValue: ['set'], argHints });
}

function _runtimeConfigContext() {
  const entries = _cliConfigEntries();
  const optionHints = entries.map(entry => _runtimeHint(entry.key, entry.description));
  const argHints = {
    list: [],
    get: optionHints,
    set: optionHints,
    __positional__: [
      _runtimeHint('list', 'Show all current user config'),
      _runtimeHint('get', 'Show one user config value', 'get '),
      _runtimeHint('set', 'Set one user config value', 'set '),
    ],
  };
  const sequenceArgHints = {};
  entries.forEach((entry) => {
    sequenceArgHints[`set ${entry.key}`] = Array.isArray(entry.values)
      ? entry.values.map(value => _runtimeHint(value, entry.description))
      : [_runtimePlaceholderHint(entry.valueHelp || '<value>', entry.description)];
    sequenceArgHints[`get ${entry.key}`] = [];
    if (Array.isArray(entry.values)) entry.values.forEach(value => { argHints[value] = []; });
  });
  return _runtimeContextSpec({ expectsValue: ['get', 'set'], argHints, sequenceArgHints });
}

function _runtimeVariableHints(description = 'Session variable') {
  const variables = Array.isArray(sessionVariables) ? sessionVariables : [];
  return variables.map(variable => {
    const name = String(variable && variable.name || '').trim();
    const value = String(variable && variable.value || '').trim();
    return _runtimeHint(name, value ? `${description}: ${value}` : description);
  }).filter(item => item.value);
}

function _runtimeVarContext() {
  const variableHints = _runtimeVariableHints('Current value');
  const starterNames = ['HOST', 'PORT', 'IP_ADDR'];
  const currentNames = new Set(variableHints.map(item => String(item.value || '').toUpperCase()));
  const starterHints = starterNames
    .filter(name => !currentNames.has(name))
    .map(name => _runtimeHint(name, `Common ${name.toLowerCase()} value`));
  const sequenceArgHints = {};
  variableHints.concat(starterNames.map(name => _runtimeHint(name))).forEach(item => {
    const name = String(item && item.value || '').trim();
    if (name) {
      sequenceArgHints[`set ${name.toLowerCase()}`] = [_runtimePlaceholderHint('<value>', `Value for ${name}`)];
      sequenceArgHints[`unset ${name.toLowerCase()}`] = [];
    }
  });
  const argHints = {
    list: [],
    set: variableHints.concat(starterHints),
    unset: variableHints,
    __positional__: [
      _runtimeHint('list', 'Show session variables'),
      _runtimeHint('set', 'Set a session variable', 'set '),
      _runtimeHint('unset', 'Remove a session variable', 'unset '),
    ],
  };
  return _runtimeContextSpec({
    expectsValue: ['set', 'unset'],
    argHints,
    sequenceArgHints,
    closeAfter: {
      list: 0,
      set: 2,
      unset: 1,
    },
  });
}

function _runtimeWordlistContext() {
  const wordlists = (typeof acWordlists !== 'undefined' && Array.isArray(acWordlists)) ? acWordlists : [];
  const categoryHints = [];
  const seenCategories = new Set();
  wordlists.forEach((item) => {
    const category = String(item && (item.wordlist_category || item.category) || '').trim();
    if (!category || seenCategories.has(category.toLowerCase())) return;
    seenCategories.add(category.toLowerCase());
    categoryHints.push(_runtimeHint(category, 'Wordlist category'));
  });
  const pathHints = wordlists.map(item => _runtimeHint(
    String(item && item.name || item && item.label || item && item.value || ''),
    String(item && item.description || 'Installed wordlist'),
  )).filter(item => item.value);
  return _runtimeContextSpec({
    argHints: {
      list: categoryHints,
      path: pathHints,
    },
  });
}

function _runtimeProjectRefHints(statuses = []) {
  const wanted = new Set((Array.isArray(statuses) ? statuses : []).map(status => String(status || '').toLowerCase()));
  const projects = typeof _readAutocompleteProjects === 'function' ? _readAutocompleteProjects() : [];
  return projects
    .filter((project) => {
      const status = String(project && project.status || '').toLowerCase();
      return !wanted.size || wanted.has(status);
    })
    .map((project) => {
      const value = String(project && project.value || '').trim();
      if (!value) return null;
      const name = String(project && project.name || '').trim();
      const status = String(project && project.status || '').trim();
      const suffix = status ? ` · ${status}` : '';
      return _runtimeHint(value, `${name || value}${suffix}`);
    })
    .filter(Boolean);
}

function _runtimeProjectContext(baseSpec = {}) {
  const spec = _cloneRuntimeSpec(baseSpec);
  spec.subcommands = spec.subcommands && typeof spec.subcommands === 'object' ? spec.subcommands : {};
  const setProjectHints = (name, hints) => {
    const subSpec = spec.subcommands[name] && typeof spec.subcommands[name] === 'object'
      ? _cloneRuntimeSpec(spec.subcommands[name])
      : {};
    if (hints.length) {
      subSpec.arg_hints = Object.assign({}, subSpec.arg_hints || {}, { __positional__: hints });
      spec.subcommands[name] = subSpec;
    } else {
      spec.subcommands[name] = _runtimeMergeContextSpec(subSpec, _runtimeContextSpec());
    }
  };
  setProjectHints('use', _runtimeProjectRefHints(['active']));
  setProjectHints('rename', _runtimeProjectRefHints());
  setProjectHints('archive', _runtimeProjectRefHints(['active']));
  setProjectHints('unarchive', _runtimeProjectRefHints(['archived']));
  setProjectHints('delete', _runtimeProjectRefHints());
  return spec;
}

function getRuntimeAutocompleteContext(baseRegistry = {}) {
  const context = {};
  _runtimeActiveBuiltinRoots(baseRegistry).forEach((root) => {
    if (baseRegistry[root] && _runtimeSpecEnabledForFeatures(root, baseRegistry[root])) {
      context[root] = _cloneRuntimeSpec(baseRegistry[root]);
    }
  });
  const lookupHints = _runtimeCommandLookupHints(baseRegistry);
  context.theme = _runtimeMergeContextSpec(baseRegistry.theme, _runtimeThemeContext());
  context.config = _runtimeMergeContextSpec(baseRegistry.config, _runtimeConfigContext());
  context.var = _runtimeMergeContextSpec(baseRegistry.var, _runtimeVarContext());
  if (baseRegistry.wordlist) {
    context.wordlist = _runtimeMergeContextSpec(baseRegistry.wordlist, _runtimeWordlistContext());
  }
  if (baseRegistry.workflow) {
    context.workflow = _runtimeMergeContextSpec(baseRegistry.workflow, _runtimeWorkflowContext());
  }
  if (baseRegistry.project) {
    context.project = _runtimeProjectContext(baseRegistry.project);
  }
  if (isWorkspaceFeatureEnabled() && baseRegistry.file) {
    context.file = _runtimeMergeContextSpec(baseRegistry.file, _runtimeWorkspaceContext());
  }
  if (isWorkspaceFeatureEnabled() && baseRegistry.cat) {
    context.cat = _runtimeMergeContextSpec(baseRegistry.cat, _runtimeContextSpec({
      argHints: { __positional__: _runtimeWorkspaceFilePathHints() },
      workspacePathArgKinds: { __positional__: ['file'] },
    }));
  }
  if (isWorkspaceFeatureEnabled() && baseRegistry.cd) {
    context.cd = _runtimeMergeContextSpec(baseRegistry.cd, _runtimeContextSpec({
      argHints: { __positional__: _runtimeWorkspaceNavigableDirectoryHints() },
      workspacePathArgKinds: { __positional__: ['directory'] },
    }));
  }
  if (isWorkspaceFeatureEnabled() && baseRegistry.ls) {
    context.ls = _runtimeMergeContextSpec(baseRegistry.ls, _runtimeContextSpec({
      argHints: { __positional__: [_runtimeHint('-l', 'Long listing'), _runtimeHint('-R', 'Recursive listing')].concat(_runtimeWorkspaceNavigableDirectoryHints()) },
      workspacePathArgKinds: { __positional__: ['directory'] },
    }));
  }
  if (isWorkspaceFeatureEnabled() && baseRegistry.ll) {
    context.ll = _runtimeMergeContextSpec(baseRegistry.ll, _runtimeContextSpec({
      argHints: { __positional__: [_runtimeHint('-R', 'Recursive listing')].concat(_runtimeWorkspaceNavigableDirectoryHints()) },
      workspacePathArgKinds: { __positional__: ['directory'] },
    }));
  }
  if (isWorkspaceFeatureEnabled() && baseRegistry.mkdir) {
    context.mkdir = _runtimeMergeContextSpec(baseRegistry.mkdir, _runtimeContextSpec({
      argHints: { __positional__: _runtimeWorkspaceDirectoryHints().concat([_runtimePlaceholderHint('<folder>', 'New session folder')]) },
      workspacePathArgKinds: { __positional__: ['directory'] },
    }));
  }
  if (isWorkspaceFeatureEnabled() && baseRegistry.rm) {
    const deleteHints = _runtimeWorkspaceFileHints().concat(_runtimeWorkspaceDirectoryHints());
    context.rm = _runtimeMergeContextSpec(baseRegistry.rm, _runtimeContextSpec({
      argHints: {
        __positional__: [_runtimeHint('-r', 'Remove folders recursively'), _runtimeHint('-rf', 'Remove folders recursively')].concat(deleteHints),
      },
      workspacePathArgKinds: { __positional__: ['any'] },
    }));
  }
  if (isWorkspaceFeatureEnabled() && baseRegistry.mv) {
    const moveSourceHints = _runtimeWorkspaceMoveSourceHints();
    context.mv = _runtimeMergeContextSpec(baseRegistry.mv, _runtimeContextSpec({
      argHints: { __positional__: moveSourceHints },
      sequenceArgHints: _runtimeWorkspaceMoveSequenceHints(
        'mv',
        moveSourceHints,
        _runtimeWorkspaceMoveDestinationHints(),
      ),
      workspacePathArgKinds: { __positional__: ['any', 'directory'] },
    }));
  }
  ['grep', 'head', 'tail', 'sort', 'uniq'].forEach((root) => {
    if (isWorkspaceFeatureEnabled() && baseRegistry[root]) {
      context[root] = _runtimeMergeContextSpec(baseRegistry[root], _runtimeContextSpec({
        argHints: { __positional__: _runtimeWorkspaceFilePathHints() },
        workspacePathArgKinds: { __positional__: ['file'] },
      }));
    }
  });
  if (isWorkspaceFeatureEnabled() && baseRegistry.wc) {
    context.wc = _runtimeMergeContextSpec(baseRegistry.wc, _runtimeContextSpec({
      argHints: { '-l': _runtimeWorkspaceFilePathHints() },
      sequenceArgHints: { '-l': _runtimeWorkspaceFilePathHints() },
      workspacePathArgKinds: { __positional__: ['file'], '-l': ['file'] },
    }));
  }
  context.man = _runtimeMergeContextSpec(baseRegistry.man, _runtimeContextSpec({
    argHints: { __positional__: lookupHints },
  }));
  context.commands = _runtimeMergeContextSpec(baseRegistry.commands, _runtimeContextSpec({
    expectsValue: ['info'],
    argHints: { info: _runtimeCommandLookupHints(baseRegistry, 'command details') },
  }));
  context.which = _runtimeMergeContextSpec(baseRegistry.which, _runtimeContextSpec({
    argHints: { __positional__: _runtimeCommandLookupHints(baseRegistry, 'command path') },
  }));
  context.type = _runtimeMergeContextSpec(baseRegistry.type, _runtimeContextSpec({
    argHints: { __positional__: _runtimeCommandLookupHints(baseRegistry, 'command type') },
  }));
  return context;
}

function getRuntimeAutocompleteItems(ctx, buildItem, filterItems) {
  const token = String(ctx && ctx.currentToken || '');
  const dollarIndex = token.lastIndexOf('$');
  if (dollarIndex < 0 || !buildItem || !filterItems) return [];
  const afterDollar = token.slice(dollarIndex + 1);
  const braced = afterDollar.startsWith('{');
  const query = braced ? afterDollar.slice(1) : afterDollar;
  if (!/^\{?[A-Za-z_][A-Za-z0-9_]*$/.test(afterDollar) && afterDollar !== '{') return [];
  const variables = Array.isArray(sessionVariables) ? sessionVariables : [];
  const items = variables.map(variable => {
    const name = String(variable && variable.name || '').trim();
    if (!name) return null;
    const label = braced ? '${' + name + '}' : '$' + name;
    return buildItem({
      value: label,
      label,
      description: String(variable && variable.value || ''),
      replaceStart: ctx.tokenStart + dollarIndex,
      replaceEnd: ctx.tokenEnd,
      insertValue: label,
    });
  }).filter(Boolean);
  return filterItems(items, braced ? '${' + query : '$' + query);
}

async function loadSessionVariables() {
  try {
    const resp = await apiFetch('/session/variables');
    if (resp && resp.ok === false) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    sessionVariables = Array.isArray(data.variables) ? data.variables : [];
  } catch (err) {
    logClientError('failed to load /session/variables', err);
    sessionVariables = [];
  }
  return sessionVariables;
}
