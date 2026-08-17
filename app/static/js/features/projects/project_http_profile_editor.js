// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Shared form builder for Project Assessment HTTP profiles.

function valueOf(reference) {
  if (reference && typeof reference === 'object') return String(reference.name || '');
  return String(reference || '');
}

function listValue(values) {
  return (Array.isArray(values) ? values : []).map(value => String(value || '')).filter(Boolean).join('\n');
}

function lines(value) {
  return String(value || '')
    .split(/\r?\n/)
    .map(item => item.trim())
    .filter(Boolean);
}

function field(labelText, control, description = '') {
  const label = document.createElement('label');
  label.className = 'project-http-profile-field';
  const text = document.createElement('span');
  text.className = 'project-http-profile-field-label';
  text.textContent = labelText;
  label.append(text, control);
  if (description) {
    const help = document.createElement('small');
    help.textContent = description;
    label.appendChild(help);
  }
  return label;
}

function textInput(value = '', options = {}) {
  const input = document.createElement('input');
  input.type = options.type || 'text';
  input.className = 'form-control';
  input.value = String(value || '');
  input.placeholder = options.placeholder || '';
  input.autocomplete = 'off';
  input.autocapitalize = 'none';
  input.autocorrect = 'off';
  input.spellcheck = false;
  if (options.min !== undefined) input.min = String(options.min);
  if (options.max !== undefined) input.max = String(options.max);
  return input;
}

function secretSelect(reference = '', secrets = []) {
  const select = document.createElement('select');
  select.className = 'form-select';
  const empty = document.createElement('option');
  empty.value = '';
  empty.textContent = 'Not set';
  select.appendChild(empty);

  const currentName = valueOf(reference);
  const names = new Set();
  (Array.isArray(secrets) ? secrets : []).forEach((secret) => {
    const name = String(secret?.name || '').trim();
    if (!name || names.has(name)) return;
    names.add(name);
    const aliases = (Array.isArray(secret?.consumer_envs) ? secret.consumer_envs : [])
      .map(value => String(value || '').trim())
      .filter(value => value && value !== name);
    const option = document.createElement('option');
    option.value = name;
    option.textContent = aliases.length ? `${name} — ${aliases.join(', ')}` : name;
    select.appendChild(option);
  });
  if (currentName && !names.has(currentName)) {
    const unavailable = document.createElement('option');
    unavailable.value = currentName;
    unavailable.textContent = `${currentName} — unavailable`;
    select.appendChild(unavailable);
  }
  select.value = currentName;
  return select;
}

function textarea(value = '', placeholder = '') {
  const input = document.createElement('textarea');
  input.className = 'form-control project-http-profile-textarea nice-scroll';
  input.value = String(value || '');
  input.placeholder = placeholder;
  input.rows = 3;
  input.autocomplete = 'off';
  input.autocapitalize = 'none';
  input.autocorrect = 'off';
  input.spellcheck = false;
  return input;
}

function headerValue(headers) {
  return (Array.isArray(headers) ? headers : [])
    .map(header => `${String(header?.name || '')} = ${String(header?.secret_name || '')}`)
    .filter(line => !line.startsWith(' = '))
    .join('\n');
}

function parseHeaders(value) {
  return lines(value).map((line) => {
    const separator = line.indexOf('=');
    if (separator <= 0 || !line.slice(separator + 1).trim()) {
      throw new Error('Custom headers must use Header-Name = SECRET_NAME, one per line.');
    }
    return {
      name: line.slice(0, separator).trim(),
      secret_name: line.slice(separator + 1).trim(),
    };
  });
}

function profileForm(profile = null, options = {}) {
  const current = profile || {};
  const refs = current.secret_refs || {};
  const files = current.file_refs || {};
  const secrets = Array.isArray(options.secrets) ? options.secrets : [];
  const controls = {
    name: textInput(current.name, { placeholder: 'Authenticated application user' }),
    role: textInput(current.role || 'anonymous', { placeholder: 'anonymous' }),
    baseUrl: textInput(current.base_url, { type: 'url', placeholder: 'https://app.example.com/' }),
    scopeRoots: textarea(listValue(current.scope_roots), 'https://app.example.com/\nhttps://app.example.com/api/'),
    allowedHosts: textarea(listValue(current.allowed_hosts), 'app.example.com'),
    includePaths: textarea(listValue(current.include_paths), '/app\n/api'),
    excludePaths: textarea(listValue(current.exclude_paths), '/logout\n/admin/destructive'),
    rate: textInput(current.rate_limit_per_second || 10, { type: 'number', min: 1, max: 1000 }),
    concurrency: textInput(current.concurrency || 5, { type: 'number', min: 1, max: 100 }),
    bearer: secretSelect(refs.bearer_token, secrets),
    cookie: secretSelect(refs.cookie, secrets),
    basicUsername: secretSelect(refs.basic_username, secrets),
    basicPassword: secretSelect(refs.basic_password, secrets),
    proxyAuthorization: secretSelect(refs.proxy_authorization, secrets),
    keyPassphrase: secretSelect(refs.client_key_passphrase, secrets),
    certificate: textInput(files.client_certificate, { placeholder: 'certificates/client.crt' }),
    clientKey: textInput(files.client_key, { placeholder: 'certificates/client.key' }),
    headers: textarea(headerValue(current.headers), 'X-API-Key = APP_API_KEY'),
  };
  controls.enabled = document.createElement('input');
  controls.enabled.type = 'checkbox';
  controls.enabled.checked = current.enabled !== false;

  const content = document.createElement('div');
  content.className = 'project-http-profile-editor nice-scroll';

  const identity = document.createElement('div');
  identity.className = 'project-http-profile-editor-grid';
  identity.append(
    field('Profile name', controls.name),
    field('Authentication role', controls.role, 'A short label such as anonymous, member, or admin.'),
    field('Base URL', controls.baseUrl),
    field('Scope roots', controls.scopeRoots, 'One absolute HTTP(S) URL per line.'),
    field('Allowed Project hosts', controls.allowedHosts, 'One confirmed Project hostname or IP per line.'),
    field('Included paths', controls.includePaths, 'Optional URL path prefixes, one per line.'),
    field('Excluded paths', controls.excludePaths, 'Optional URL path prefixes, one per line.'),
    field('Requests per second', controls.rate),
    field('Concurrency', controls.concurrency),
  );

  const authHeading = document.createElement('div');
  authHeading.className = 'project-http-profile-editor-heading';
  authHeading.textContent = 'Protected references';
  const authCopy = document.createElement('p');
  authCopy.className = 'project-http-profile-editor-copy';
  const scopeLabel = options.secretScope === 'team' ? 'team Secrets' : 'personal Secrets';
  authCopy.textContent = secrets.length
    ? `Choose from the ${scopeLabel} available to this Project. Basic authentication needs separate username and password Secrets. Values stay in Options and are never shown here.`
    : `No ${scopeLabel} are available to this Project. Use Manage Secrets before adding protected references.`;
  const auth = document.createElement('div');
  auth.className = 'project-http-profile-editor-grid';
  auth.append(
    field('Bearer token Secret', controls.bearer),
    field('Cookie Secret', controls.cookie),
    field('Basic username Secret', controls.basicUsername),
    field('Basic password Secret', controls.basicPassword),
    field('Proxy authorization Secret', controls.proxyAuthorization),
    field('Client-key passphrase Secret', controls.keyPassphrase),
    field('Client certificate Files path', controls.certificate),
    field('Client key Files path', controls.clientKey),
    field('Custom header Secrets', controls.headers, 'Use Header-Name = SECRET_NAME, one per line.'),
  );

  const enabled = document.createElement('label');
  enabled.className = 'form-check project-http-profile-enabled';
  const enabledCopy = document.createElement('span');
  enabledCopy.textContent = 'Allow this profile to be selected for assessment runs';
  enabled.append(controls.enabled, enabledCopy);

  const advanced = [];
  if (current.proxy_configured) advanced.push('proxy');
  if (current.login_workflow_id) advanced.push('login workflow');
  if (Number(current.capture_rule_count || 0)) advanced.push('token capture');
  if (advanced.length) {
    const note = document.createElement('p');
    note.className = 'project-http-profile-editor-copy is-warning';
    note.textContent = `This profile also has ${advanced.join(', ')} context configured through the API. These values are preserved when you save.`;
    content.appendChild(note);
  }
  const error = document.createElement('div');
  error.className = 'project-http-profile-editor-error';
  error.hidden = true;
  content.append(identity, authHeading, authCopy, auth, enabled, error);
  return { content, controls, error };
}

function payloadFromForm(controls) {
  const secretRefs = {};
  [
    ['bearer_token', controls.bearer],
    ['cookie', controls.cookie],
    ['basic_username', controls.basicUsername],
    ['basic_password', controls.basicPassword],
    ['proxy_authorization', controls.proxyAuthorization],
    ['client_key_passphrase', controls.keyPassphrase],
  ].forEach(([slot, input]) => {
    const value = String(input.value || '').trim();
    if (value) secretRefs[slot] = value;
  });
  const fileRefs = {};
  const certificate = String(controls.certificate.value || '').trim();
  const clientKey = String(controls.clientKey.value || '').trim();
  if (certificate) fileRefs.client_certificate = certificate;
  if (clientKey) fileRefs.client_key = clientKey;
  return {
    name: String(controls.name.value || '').trim(),
    role: String(controls.role.value || '').trim(),
    base_url: String(controls.baseUrl.value || '').trim(),
    scope_roots: lines(controls.scopeRoots.value),
    allowed_hosts: lines(controls.allowedHosts.value),
    include_paths: lines(controls.includePaths.value),
    exclude_paths: lines(controls.excludePaths.value),
    rate_limit_per_second: Number(controls.rate.value || 0),
    concurrency: Number(controls.concurrency.value || 0),
    headers: parseHeaders(controls.headers.value),
    secret_refs: secretRefs,
    file_refs: fileRefs,
    enabled: controls.enabled.checked,
  };
}

function restoreFocus(target) {
  if (!target?.isConnected || target.disabled || typeof target.focus !== 'function') return;
  try {
    target.focus({ preventScroll: true });
  } catch (_) {
    target.focus();
  }
}

async function openHttpProfileEditor(context, options = {}) {
  const ctx = context || {};
  const projectId = String(options.projectId || '');
  const profile = options.profile || null;
  if (
    !projectId
    || typeof ctx.showConfirm !== 'function'
    || typeof ctx.projectWorkspaceRequest !== 'function'
  ) return false;
  const secretResponse = await ctx.projectWorkspaceRequest('/session/secrets', { cache: 'no-store' });
  if (!secretResponse.ok) {
    if (typeof ctx.projectResponseError === 'function') {
      throw await ctx.projectResponseError(secretResponse, 'Could not load Project-scope Secrets.');
    }
    throw new Error('Could not load Project-scope Secrets.');
  }
  const secretPayload = await secretResponse.json();
  const { content, controls, error } = profileForm(profile, {
    secrets: Array.isArray(secretPayload?.secrets) ? secretPayload.secrets : [],
    secretScope: String(secretPayload?.scope || ''),
  });
  const save = {
    id: 'save',
    label: profile ? 'Save profile' : 'Create profile',
    role: 'primary',
    onActivate: async () => {
      error.hidden = true;
      try {
        const payload = payloadFromForm(controls);
        if (!payload.name || !payload.base_url) {
          throw new Error('Profile name and base URL are required.');
        }
        if (Boolean(payload.secret_refs.basic_username) !== Boolean(payload.secret_refs.basic_password)) {
          throw new Error('Basic authentication needs both username and password Secrets.');
        }
        if (Boolean(payload.file_refs.client_certificate) !== Boolean(payload.file_refs.client_key)) {
          throw new Error('Client authentication needs both certificate and key Files paths.');
        }
        const path = profile
          ? `/projects/${encodeURIComponent(projectId)}/http-profiles/${encodeURIComponent(profile.id)}`
          : `/projects/${encodeURIComponent(projectId)}/http-profiles`;
        if (profile) payload.revision = Number(profile.revision || 1);
        const resp = await ctx.projectWorkspaceRequest(path, {
          method: profile ? 'PATCH' : 'POST',
          body: JSON.stringify(payload),
        });
        if (!resp.ok) {
          if (typeof ctx.projectResponseError === 'function') {
            throw await ctx.projectResponseError(resp, 'Could not save this HTTP profile.');
          }
          throw new Error('Could not save this HTTP profile.');
        }
        await options.onSaved?.();
        return true;
      } catch (err) {
        error.textContent = err?.message || 'Could not save this HTTP profile.';
        error.hidden = false;
        return false;
      }
    },
  };
  const choice = await ctx.showConfirm({
    body: {
      text: profile ? `Edit ${profile.name || 'HTTP profile'}` : 'Create an HTTP assessment profile',
      note: 'Profiles are restricted to confirmed Project targets. Saving one does not contact the target or start a scanner.',
    },
    content,
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      save,
    ],
    defaultFocus: controls.name,
    refocusOnResolve: false,
  });
  if (choice !== 'save') restoreFocus(options.returnFocus);
  return choice === 'save';
}

export { openHttpProfileEditor, payloadFromForm, profileForm };
