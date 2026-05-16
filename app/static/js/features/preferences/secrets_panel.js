// Options modal encrypted secrets panel.

const SECRET_NAME_PATTERN = /^[A-Z][A-Z0-9_]{0,63}$/;
let _optionsSecretsLoaded = false;
let _optionsSecretsLoading = false;
let _providerStatusFocusReturn = null;

function _optionsSecretsListEl() {
  return document.getElementById('options-secrets-list');
}

function _optionsSecretsMsgEl() {
  return document.getElementById('options-secrets-msg');
}

function _providerStatusOverlayEl() {
  return document.getElementById('provider-status-overlay');
}

function _providerStatusModalEl() {
  return document.getElementById('provider-status-modal');
}

function _providerStatusBodyEl() {
  return document.getElementById('provider-status-body');
}

function _normalizeOptionsSecretName(value) {
  return String(value || '').trim().toUpperCase();
}

function _optionsSecretNameIsValid(value) {
  return SECRET_NAME_PATTERN.test(_normalizeOptionsSecretName(value));
}

function _optionsSecretsShowMsg(message, isError = false) {
  const el = _optionsSecretsMsgEl();
  if (!el) return;
  el.textContent = message || '';
  el.style.display = message ? '' : 'none';
  el.classList.toggle('is-error', Boolean(isError));
}

function _optionsSecretsSetBusy(busy) {
  _optionsSecretsLoading = Boolean(busy);
  ['options-provider-status-btn', 'options-secret-new-btn', 'options-secrets-refresh-btn'].forEach((id) => {
    const btn = document.getElementById(id);
    if (btn) btn.disabled = _optionsSecretsLoading;
  });
  _optionsSecretsListEl()?.querySelectorAll('button').forEach((btn) => {
    btn.disabled = _optionsSecretsLoading;
  });
}

function _optionsSecretConsumerLabel(secret) {
  const envs = Array.isArray(secret?.consumer_envs) ? secret.consumer_envs : [];
  if (!envs.length) return 'No consumers';
  return envs.join(', ');
}

function _optionsSecretConsumerInputValue(secret) {
  const envs = Array.isArray(secret?.consumer_envs) ? secret.consumer_envs : [];
  return envs.join(', ');
}

async function _ensureOptionsSecretCatalog() {
  if (typeof commandRegistryData !== 'undefined' && commandRegistryData) return commandRegistryData;
  if (typeof apiFetch !== 'function') return null;
  try {
    const resp = await apiFetch('/commands/catalog');
    const data = await resp.json().catch(() => ({}));
    if (resp && resp.ok === false) throw new Error(data.message || data.error || `HTTP ${resp.status}`);
    if (typeof commandRegistryData !== 'undefined') commandRegistryData = data;
    return data;
  } catch (err) {
    if (typeof logClientError === 'function') logClientError('failed to load secret consumer catalog', err);
    return null;
  }
}

function _optionsKnownSecretChoices() {
  const data = typeof commandRegistryData !== 'undefined' ? commandRegistryData : null;
  const commands = Array.isArray(data?.commands) ? data.commands : [];
  const secretConsumers = Array.isArray(data?.secret_consumers) ? data.secret_consumers : [];
  const byName = new Map();
  const visitDeclaration = (consumerName, declaration) => {
    const env = _normalizeOptionsSecretName(declaration?.env);
    if (!_optionsSecretNameIsValid(env)) return;
    const injectEnv = _normalizeOptionsSecretName(declaration?.inject_env || env);
    const fallbackEnvs = (Array.isArray(declaration?.fallback_envs) ? declaration.fallback_envs : [])
      .map((item) => _normalizeOptionsSecretName(item))
      .filter((item, index, arr) => _optionsSecretNameIsValid(item) && item !== env && arr.indexOf(item) === index);
    const existing = byName.get(env) || {
      name: env,
      roots: [],
      inject_envs: [],
      fallback_envs: [],
      optional: true,
    };
    if (consumerName && !existing.roots.includes(consumerName)) existing.roots.push(consumerName);
    if (injectEnv && !existing.inject_envs.includes(injectEnv)) existing.inject_envs.push(injectEnv);
    fallbackEnvs.forEach((fallbackEnv) => {
      if (!existing.fallback_envs.includes(fallbackEnv)) existing.fallback_envs.push(fallbackEnv);
    });
    existing.optional = existing.optional && Boolean(declaration?.optional);
    byName.set(env, existing);
  };
  if (secretConsumers.length) {
    secretConsumers.forEach((consumer) => {
      const name = String(consumer?.consumer || consumer?.root || consumer?.provider || '').trim();
      visitDeclaration(name, consumer);
    });
  } else {
    commands.forEach((command) => {
      const root = String(command?.root || '').trim();
      const declarations = Array.isArray(command?.requires_secrets) ? command.requires_secrets : [];
      declarations.forEach((declaration) => {
        visitDeclaration(root, declaration);
      });
    });
  }
  return Array.from(byName.values()).sort((left, right) => left.name.localeCompare(right.name));
}

function _optionsSecretChoiceDescription(choice) {
  if (!choice) return '';
  const roots = Array.isArray(choice.roots) && choice.roots.length ? choice.roots.join(', ') : 'configured commands';
  const injects = Array.isArray(choice.inject_envs) && choice.inject_envs.length ? choice.inject_envs : [];
  const fallbackEnvs = Array.isArray(choice.fallback_envs) && choice.fallback_envs.length ? choice.fallback_envs : [];
  const injected = injects.length && !injects.includes(choice.name)
    ? ` It is passed to the command as ${injects.join(', ')}.`
    : '';
  const fallback = fallbackEnvs.length ? ` Also accepts existing ${fallbackEnvs.join(', ')} secrets.` : '';
  return `Used by ${roots}.${injected}${fallback}`.trim();
}

function _optionsProviderSecretNames(secrets = []) {
  const names = new Set();
  secrets.forEach((secret) => {
    const name = _normalizeOptionsSecretName(secret?.name);
    if (name) names.add(name);
    const envs = Array.isArray(secret?.consumer_envs) ? secret.consumer_envs : [];
    envs.forEach((env) => {
      const normalized = _normalizeOptionsSecretName(env);
      if (normalized) names.add(normalized);
    });
  });
  return names;
}

function _optionsProviderPrimaryNames(provider) {
  const env = _normalizeOptionsSecretName(provider?.secret_env);
  return env ? [env] : [];
}

function _optionsProviderLookupNames(provider) {
  return (Array.isArray(provider?.secret_env_names) && provider.secret_env_names.length
    ? provider.secret_env_names
    : [provider?.secret_env, ...(Array.isArray(provider?.secret_env_aliases) ? provider.secret_env_aliases : [])])
    .map((item) => _normalizeOptionsSecretName(item))
    .filter((item, index, arr) => _optionsSecretNameIsValid(item) && arr.indexOf(item) === index);
}

function _optionsProviderStatus(provider, secretNames) {
  const acceptedNames = _optionsProviderPrimaryNames(provider);
  const lookupNames = _optionsProviderLookupNames(provider);
  const needsSecret = Boolean(provider?.requires_secret || lookupNames.length);
  const hasStoredSecret = lookupNames.some((name) => secretNames.has(name));
  const configured = hasStoredSecret || !needsSecret || Boolean(provider?.optional_secret);
  return {
    acceptedNames,
    configured,
    label: configured ? 'Usable' : 'Not configured',
  };
}

function _optionsChip(text, className = '', opts = {}) {
  const chip = document.createElement('span');
  chip.className = `badge badge-tone-muted options-secret-chip${className ? ` ${className}` : ''}`;
  chip.textContent = text;
  if (opts.title) chip.title = opts.title;
  return chip;
}

function _optionsStoredSecretForProviderName(displayName, provider, secrets = []) {
  const primaryName = _normalizeOptionsSecretName(displayName);
  const lookupNames = [
    primaryName,
    ..._optionsProviderLookupNames(provider),
  ].filter((item, index, arr) => item && arr.indexOf(item) === index);
  const hasConsumer = (secret, name) => {
    const envs = Array.isArray(secret?.consumer_envs) ? secret.consumer_envs : [];
    return envs.some((env) => _normalizeOptionsSecretName(env) === name);
  };
  for (const name of lookupNames) {
    const exact = secrets.find((secret) => _normalizeOptionsSecretName(secret?.name) === name);
    if (exact) return exact;
    const consumerMatch = secrets.find((secret) => hasConsumer(secret, name));
    if (consumerMatch) return consumerMatch;
  }
  return null;
}

function _optionsSecretLink(name, secret = null) {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'chip chip-action options-secret-chip options-secret-link';
  btn.textContent = name;
  btn.title = secret ? `Replace ${_normalizeOptionsSecretName(secret.name) || name}` : `Add ${name}`;
  btn.addEventListener('click', () => {
    closeProviderStatusModal({ refocus: false });
    const editorOptions = secret ? { secret } : { name };
    openSecretEditor(editorOptions).catch((err) => {
      _optionsSecretsShowMsg(err.message || 'Unable to open secret editor', true);
    });
  });
  return btn;
}

function _appendOptionsProviderChips(parent, items, emptyText) {
  if (!items.length) {
    parent.appendChild(_optionsChip(emptyText, 'is-muted'));
    return;
  }
  items.forEach((item) => parent.appendChild(_optionsChip(item)));
}

function _optionsProviderRow(provider, secretNames, secrets = []) {
  const status = _optionsProviderStatus(provider, secretNames);
  const row = document.createElement('div');
  row.className = 'options-provider-row';
  row.dataset.status = status.configured ? 'usable' : 'needs-config';

  const header = document.createElement('div');
  header.className = 'options-provider-row-header';

  const title = document.createElement('div');
  title.className = 'options-provider-name';
  title.textContent = String(provider?.label || provider?.id || 'Provider');
  header.appendChild(title);

  const badge = document.createElement('span');
  badge.className = `badge options-provider-status ${
    status.configured ? 'badge-tone-green is-usable' : 'badge-tone-muted is-needed'
  }`;
  badge.textContent = status.label;
  header.appendChild(badge);
  row.appendChild(header);

  const meta = document.createElement('div');
  meta.className = 'options-provider-meta';
  meta.textContent = String(provider?.access_note || (status.acceptedNames.length ? 'Account-backed' : 'Free public lookup'));
  row.appendChild(meta);

  const entityWrap = document.createElement('div');
  entityWrap.className = 'options-secret-chips';
  const uses = Array.isArray(provider?.uses)
    ? provider.uses.map((item) => String(item || '').trim()).filter(Boolean)
    : [];
  const entityTypes = Array.isArray(provider?.entity_types)
    ? provider.entity_types.map((item) => String(item || '').toUpperCase())
    : [];
  _appendOptionsProviderChips(
    entityWrap,
    uses.length ? uses : entityTypes,
    'No provider uses',
  );
  row.appendChild(entityWrap);

  const secretWrap = document.createElement('div');
  secretWrap.className = 'options-secret-chips';
  if (status.acceptedNames.length) {
    status.acceptedNames.forEach((name) => {
      secretWrap.appendChild(_optionsSecretLink(
        name,
        _optionsStoredSecretForProviderName(name, provider, secrets),
      ));
    });
  } else {
    secretWrap.appendChild(_optionsChip('No secret needed', 'is-muted'));
  }
  row.appendChild(secretWrap);

  return row;
}

async function _loadOptionsSecretsForProviderStatus() {
  const resp = await apiFetch('/session/secrets', { cache: 'no-store' });
  const data = await resp.json().catch(() => ({}));
  if (resp && resp.ok === false) throw new Error(data.message || data.error || `HTTP ${resp.status}`);
  return Array.isArray(data.secrets) ? data.secrets : [];
}

function isProviderStatusModalOpen() {
  const overlay = _providerStatusOverlayEl();
  return !!(overlay && overlay.classList && !overlay.classList.contains('u-hidden'));
}

function closeProviderStatusModal({ refocus = true } = {}) {
  const overlay = _providerStatusOverlayEl();
  if (!overlay) return;
  overlay.classList.add('u-hidden');
  overlay.setAttribute('aria-hidden', 'true');
  if (typeof hideModalOverlay === 'function') hideModalOverlay(overlay);
  if (refocus) {
    const target = _providerStatusFocusReturn;
    if (target && typeof target.focus === 'function') {
      try { target.focus({ preventScroll: true }); } catch (_) { /* non-critical */ }
    } else if (typeof refocusComposerAfterAction === 'function') {
      refocusComposerAfterAction({ preventScroll: true });
    }
  }
  _providerStatusFocusReturn = null;
}

async function openProviderStatusModal() {
  const overlay = _providerStatusOverlayEl();
  const body = _providerStatusBodyEl();
  if (!overlay || !body) return null;
  _optionsSecretsShowMsg('');
  try {
    const [catalog, secrets] = await Promise.all([
      _ensureOptionsSecretCatalog(),
      _loadOptionsSecretsForProviderStatus(),
    ]);
    const providers = Array.isArray(catalog?.intel_providers) ? catalog.intel_providers : [];
    const secretNames = _optionsProviderSecretNames(secrets);
    const usableCount = providers.filter((provider) => _optionsProviderStatus(provider, secretNames).configured).length;
    const needsCount = Math.max(0, providers.length - usableCount);

    const summary = document.createElement('div');
    summary.className = 'options-provider-summary';
    summary.textContent = providers.length
      ? `${usableCount} usable · ${needsCount} not configured`
      : 'No intel providers are registered.';

    const list = document.createElement('div');
    list.className = 'options-provider-list';
    providers
      .slice()
      .sort((left, right) => {
        const leftStatus = _optionsProviderStatus(left, secretNames).configured ? 0 : 1;
        const rightStatus = _optionsProviderStatus(right, secretNames).configured ? 0 : 1;
        if (leftStatus !== rightStatus) return leftStatus - rightStatus;
        return String(left?.label || left?.id || '').localeCompare(String(right?.label || right?.id || ''));
      })
      .forEach((provider) => list.appendChild(_optionsProviderRow(provider, secretNames, secrets)));

    body.innerHTML = '';
    const intro = document.createElement('div');
    intro.className = 'provider-status-intro';
    intro.textContent = 'See which intel providers can run now and which need an API key in this session.';
    body.appendChild(intro);
    body.appendChild(summary);
    body.appendChild(list);

    _providerStatusFocusReturn = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : document.getElementById('options-provider-status-btn');
    overlay.classList.remove('u-hidden');
    overlay.setAttribute('aria-hidden', 'false');
    if (typeof showModalOverlay === 'function') showModalOverlay(overlay, 'flex');
    _providerStatusModalEl()?.querySelector('.provider-status-close')?.focus({ preventScroll: true });
    return true;
  } catch (err) {
    _optionsSecretsShowMsg(`Failed to load provider status — ${err.message || 'network error'}`, true);
    return null;
  }
}

function _optionsSecretUpdatedLabel(value) {
  const raw = String(value || '').trim();
  if (!raw) return 'Updated unknown';
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return `Updated ${raw}`;
  return `Updated ${date.toLocaleString()}`;
}

function _optionsSecretChips(secret) {
  const wrap = document.createElement('div');
  wrap.className = 'options-secret-chips';
  const envs = Array.isArray(secret?.consumer_envs) ? secret.consumer_envs : [];
  if (!envs.length) {
    const chip = document.createElement('span');
    chip.className = 'badge badge-tone-muted options-secret-chip is-muted';
    chip.textContent = 'no consumers';
    wrap.appendChild(chip);
    return wrap;
  }
  envs.forEach((env) => {
    const chip = document.createElement('span');
    chip.className = 'badge badge-tone-muted options-secret-chip';
    chip.textContent = String(env || '').trim();
    wrap.appendChild(chip);
  });
  return wrap;
}

function _renderOptionsSecrets(secrets = []) {
  const list = _optionsSecretsListEl();
  if (!list) return;
  list.innerHTML = '';
  if (!secrets.length) {
    const empty = document.createElement('div');
    empty.className = 'options-secret-empty';
    empty.textContent = 'No secrets stored for this session.';
    list.appendChild(empty);
    return;
  }
  secrets.forEach((secret) => {
    const row = document.createElement('div');
    row.className = 'options-secret-row';

    const body = document.createElement('div');
    body.className = 'options-secret-row-body';

    const title = document.createElement('div');
    title.className = 'options-secret-name';
    title.textContent = String(secret?.name || '');
    body.appendChild(title);
    body.appendChild(_optionsSecretChips(secret));

    const meta = document.createElement('div');
    meta.className = 'options-secret-meta';
    meta.textContent = _optionsSecretUpdatedLabel(secret?.updated_at);
    body.appendChild(meta);

    const actions = document.createElement('div');
    actions.className = 'options-secret-actions';

    const edit = document.createElement('button');
    edit.type = 'button';
    edit.className = 'btn btn-secondary btn-compact';
    edit.textContent = 'Edit';
    edit.addEventListener('click', () => {
      openSecretEditor({ secret }).catch((err) => {
        _optionsSecretsShowMsg(err.message || 'Unable to edit secret', true);
      });
    });
    actions.appendChild(edit);

    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'btn btn-secondary btn-compact';
    del.textContent = 'Delete';
    del.addEventListener('click', () => {
      deleteOptionsSecret(String(secret?.name || '')).catch((err) => {
        _optionsSecretsShowMsg(err.message || 'Unable to delete secret', true);
      });
    });
    actions.appendChild(del);

    row.appendChild(body);
    row.appendChild(actions);
    list.appendChild(row);
  });
}

async function refreshOptionsSecrets({ force = false } = {}) {
  if (_optionsSecretsLoading) return;
  if (_optionsSecretsLoaded && !force) return;
  _optionsSecretsSetBusy(true);
  _optionsSecretsShowMsg('');
  try {
    const resp = await apiFetch('/session/secrets', { cache: 'no-store' });
    const data = await resp.json().catch(() => ({}));
    if (resp && resp.ok === false) throw new Error(data.message || data.error || `HTTP ${resp.status}`);
    _renderOptionsSecrets(Array.isArray(data.secrets) ? data.secrets : []);
    _optionsSecretsLoaded = true;
  } catch (err) {
    _renderOptionsSecrets([]);
    _optionsSecretsShowMsg(`Failed to load secrets — ${err.message || 'network error'}`, true);
  } finally {
    _optionsSecretsSetBusy(false);
  }
}

function invalidateOptionsSecrets() {
  _optionsSecretsLoaded = false;
}

function _optionsSecretInput(labelText, input) {
  const label = document.createElement('label');
  label.className = 'options-secret-field';
  const labelSpan = document.createElement('span');
  labelSpan.className = 'options-secret-field-label';
  labelSpan.textContent = labelText;
  label.appendChild(labelSpan);
  label.appendChild(input);
  return label;
}

async function openSecretEditor({ secret = null, name = '', source = 'options' } = {}) {
  if (typeof showConfirm !== 'function') return null;
  await _ensureOptionsSecretCatalog();
  const existingName = _normalizeOptionsSecretName(secret?.name || name);
  const isExisting = Boolean(secret && secret.name);
  const lockName = isExisting || (source === 'terminal' && Boolean(existingName));
  const knownChoices = _optionsKnownSecretChoices();
  const knownNames = new Set(knownChoices.map((item) => item.name));
  const startsCustom = Boolean(existingName && !knownNames.has(existingName));

  const nameSelect = document.createElement('select');
  nameSelect.className = 'form-select';
  nameSelect.disabled = lockName;
  nameSelect.autocomplete = 'off';
  if (!existingName) {
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = knownChoices.length ? 'Choose an API key' : 'No app tool secrets found';
    nameSelect.appendChild(placeholder);
  }
  knownChoices.forEach((choice) => {
    const option = document.createElement('option');
    option.value = choice.name;
    option.textContent = `${choice.name} — ${choice.roots.join(', ')}`;
    nameSelect.appendChild(option);
  });
  const customOption = document.createElement('option');
  customOption.value = '__custom__';
  customOption.textContent = 'Custom secret...';
  nameSelect.appendChild(customOption);
  nameSelect.value = startsCustom || (!existingName && !knownChoices.length) ? '__custom__' : existingName;

  const nameInput = document.createElement('input');
  nameInput.type = 'text';
  nameInput.className = 'options-token-input';
  nameInput.placeholder = 'CUSTOM_API_KEY';
  nameInput.value = startsCustom ? existingName : '';
  nameInput.disabled = lockName;
  nameInput.autocomplete = 'off';
  nameInput.autocapitalize = 'none';
  nameInput.autocorrect = 'off';
  nameInput.spellcheck = false;
  nameInput.inputMode = 'text';
  nameInput.setAttribute('data-bwignore', 'true');
  nameInput.setAttribute('data-1p-ignore', 'true');
  nameInput.setAttribute('data-lpignore', 'true');

  const valueInput = document.createElement('input');
  valueInput.type = 'password';
  valueInput.className = 'options-token-input';
  valueInput.placeholder = isExisting ? 'Paste replacement API key or token' : 'Paste API key or token';
  valueInput.autocomplete = 'off';
  valueInput.autocapitalize = 'none';
  valueInput.autocorrect = 'off';
  valueInput.spellcheck = false;
  valueInput.inputMode = 'text';
  valueInput.setAttribute('data-bwignore', 'true');
  valueInput.setAttribute('data-1p-ignore', 'true');
  valueInput.setAttribute('data-lpignore', 'true');

  const consumersInput = document.createElement('input');
  consumersInput.type = 'text';
  consumersInput.className = 'options-token-input';
  consumersInput.placeholder = 'Defaults to the secret name';
  consumersInput.value = _optionsSecretConsumerInputValue(secret);
  consumersInput.autocomplete = 'off';
  consumersInput.autocapitalize = 'none';
  consumersInput.autocorrect = 'off';
  consumersInput.spellcheck = false;
  consumersInput.inputMode = 'text';
  consumersInput.setAttribute('data-bwignore', 'true');
  consumersInput.setAttribute('data-1p-ignore', 'true');
  consumersInput.setAttribute('data-lpignore', 'true');

  const choiceDesc = document.createElement('div');
  choiceDesc.className = 'options-session-token-desc';

  const customWarning = document.createElement('div');
  customWarning.className = 'options-session-token-msg';
  customWarning.textContent = 'Custom secrets are stored, but commands only use them when a registry entry declares a matching consumer env.';

  const err = document.createElement('div');
  err.className = 'options-session-token-msg is-error';
  err.style.display = 'none';

  const note = document.createElement('div');
  note.className = 'options-session-token-desc';
  note.textContent = 'Stored values are replace-only and cannot be revealed from this panel.';

  const nameInputField = _optionsSecretInput('Custom secret name', nameInput);
  const consumersInputField = _optionsSecretInput('Consumer envs', consumersInput);
  function syncSecretEditorMode() {
    const selectedName = nameSelect.value;
    const selectedChoice = knownChoices.find((item) => item.name === selectedName);
    const custom = selectedName === '__custom__';
    nameInputField.style.display = custom ? '' : 'none';
    consumersInputField.style.display = custom ? '' : 'none';
    customWarning.style.display = custom ? '' : 'none';
    choiceDesc.textContent = custom
      ? 'Use this only for local command-registry overlays or future integrations.'
      : _optionsSecretChoiceDescription(selectedChoice);
  }
  nameSelect.addEventListener('change', syncSecretEditorMode);
  syncSecretEditorMode();

  const content = [
    _optionsSecretInput('Secret', nameSelect),
    choiceDesc,
    nameInputField,
    _optionsSecretInput(isExisting ? 'Replacement API key or token' : 'API key or token', valueInput),
    consumersInputField,
    customWarning,
    note,
    err,
  ];

  const saveAction = {
    id: 'save',
    label: isExisting ? 'Replace' : 'Save',
    role: 'primary',
    onActivate: async () => {
      const isCustom = nameSelect.value === '__custom__';
      const normalizedName = isCustom
        ? _normalizeOptionsSecretName(nameInput.value)
        : _normalizeOptionsSecretName(nameSelect.value);
      if (!_optionsSecretNameIsValid(normalizedName)) {
        err.textContent = isCustom
          ? 'Secret names must start with a letter and use letters, numbers, or underscores.'
          : 'Choose the API key this value belongs to.';
        err.style.display = '';
        return false;
      }
      const value = String(valueInput.value || '');
      if (!value) {
        err.textContent = 'Enter a value to store.';
        err.style.display = '';
        return false;
      }
      const consumerEnvs = String(consumersInput.value || '')
        .split(',')
        .map((item) => _normalizeOptionsSecretName(item))
        .filter(Boolean);
      const invalidEnv = consumerEnvs.find((env) => !_optionsSecretNameIsValid(env));
      if (isCustom && invalidEnv) {
        err.textContent = `Invalid consumer env: ${invalidEnv}`;
        err.style.display = '';
        return false;
      }
      try {
        const resp = await apiFetch('/session/secrets', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: normalizedName,
            value,
            consumer_envs: isCustom && consumerEnvs.length ? consumerEnvs : undefined,
          }),
        });
        const data = await resp.json().catch(() => ({}));
        if (resp && resp.ok === false) throw new Error(data.message || data.error || `HTTP ${resp.status}`);
        invalidateOptionsSecrets();
        await refreshOptionsSecrets({ force: true });
        _optionsSecretsShowMsg(
          isCustom && !isExisting
            ? `${normalizedName} saved. It is not currently used unless a command declares that consumer env.`
            : (isExisting ? `${normalizedName} replaced.` : `${normalizedName} saved.`),
        );
        return true;
      } catch (error) {
        err.textContent = `Save failed — ${error.message || 'network error'}`;
        err.style.display = '';
        return false;
      }
    },
  };

  const choice = await showConfirm({
    body: {
      text: isExisting ? `Replace ${existingName}?` : 'Store a new encrypted secret.',
      note: 'The value is sent to the server once, encrypted, and never shown here again.',
    },
    content,
    defaultFocus: isExisting || lockName ? valueInput : nameSelect,
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      saveAction,
    ],
  });

  if (choice !== 'save' && source === 'terminal') {
    _optionsSecretsShowMsg('Secret entry canceled.');
  }
  return choice;
}

async function deleteOptionsSecret(name) {
  const normalizedName = _normalizeOptionsSecretName(name);
  if (!normalizedName || typeof showConfirm !== 'function') return false;
  const choice = await showConfirm({
    body: {
      text: `Delete ${normalizedName}?`,
      note: 'Commands that require this secret will stop before launch until it is set again.',
    },
    tone: 'danger',
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      { id: 'delete', label: 'Delete', role: 'destructive' },
    ],
  });
  if (choice !== 'delete') return false;
  _optionsSecretsSetBusy(true);
  try {
    const resp = await apiFetch(`/session/secrets/${encodeURIComponent(normalizedName)}`, {
      method: 'DELETE',
    });
    const data = await resp.json().catch(() => ({}));
    if (resp && resp.ok === false) throw new Error(data.message || data.error || `HTTP ${resp.status}`);
  } finally {
    _optionsSecretsSetBusy(false);
  }
  invalidateOptionsSecrets();
  await refreshOptionsSecrets({ force: true });
  _optionsSecretsShowMsg(`${normalizedName} deleted.`);
  return true;
}

async function handleSecretCommand(cmd, tabId = null) {
  const parts = String(cmd || '').trim().split(/\s+/).filter(Boolean);
  const sub = (parts[1] || '').toLowerCase();
  if (sub !== 'set') {
    appendLine("secret: browser prompt is only used for 'secret set NAME'", '', tabId);
    appendLine("run 'secret list', 'secret unset NAME', or 'secret show-consumers' normally", '', tabId);
    setStatus('fail');
    return true;
  }
  if (parts.length !== 3) {
    appendLine('usage: secret set NAME', '', tabId);
    appendLine('Do not put the value on the command line. The browser prompt collects it safely.', 'builtin-note', tabId);
    setStatus('fail');
    return true;
  }
  const name = _normalizeOptionsSecretName(parts[2]);
  if (!_optionsSecretNameIsValid(name)) {
    appendLine('secret: secret names must start with a letter and use letters, numbers, or underscores', 'exit-fail', tabId);
    setStatus('fail');
    return true;
  }
  const choice = await openSecretEditor({ name, source: 'terminal' });
  if (choice === 'save') {
    appendLine(`${name} stored.`, 'builtin-success', tabId);
    setStatus('ok');
  } else {
    appendLine('Secret set canceled.', '', tabId);
    setStatus('idle');
  }
  return true;
}

document.getElementById('options-secret-new-btn')?.addEventListener('click', () => {
  openSecretEditor().catch((err) => _optionsSecretsShowMsg(err.message || 'Unable to add secret', true));
});

document.getElementById('options-provider-status-btn')?.addEventListener('click', () => {
  openProviderStatusModal().catch((err) => _optionsSecretsShowMsg(err.message || 'Unable to load providers', true));
});

document.getElementById('options-secrets-refresh-btn')?.addEventListener('click', () => {
  refreshOptionsSecrets({ force: true }).catch((err) => {
    _optionsSecretsShowMsg(err.message || 'Unable to refresh secrets', true);
  });
});

globalThis.refreshOptionsSecrets = refreshOptionsSecrets;
globalThis.invalidateOptionsSecrets = invalidateOptionsSecrets;
globalThis.openSecretEditor = openSecretEditor;
globalThis.openProviderStatusModal = openProviderStatusModal;
globalThis.closeProviderStatusModal = closeProviderStatusModal;
globalThis.isProviderStatusModalOpen = isProviderStatusModalOpen;
globalThis.deleteOptionsSecret = deleteOptionsSecret;
globalThis.handleSecretCommand = handleSecretCommand;
