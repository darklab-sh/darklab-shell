// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Type, permission, and lifetime controls shared by credential creation.
const SCOPE_LABELS = {
  'identity:read': 'Read identity',
  'history:read': 'Read run history and output',
  'runs:execute': 'Start and cancel commands',
  'projects:read': 'Read Projects',
  'projects:write': 'Change Projects',
  'atlas:read': 'Read Atlas',
  'atlas:write': 'Change Atlas',
  'automation:read': 'Read schedules and watchers',
  'automation:write': 'Change schedules and watchers',
  'notifications:read': 'Read notifications',
  'notifications:write': 'Change notifications',
  'secrets:manage': 'Manage Secrets',
  'teams:read': 'Read Teams',
  'teams:write': 'Manage Teams',
};

function buildCredentialCreationFields({ policy, portableCredentialsEnabled = true, field, input, expiryField, expiryInput }) {
  const host = document.createElement('div');
  const type = document.createElement('select');
  type.className = 'form-select';
  type.dataset.credentialType = '1';
  for (const [value, label] of [['portable', 'Browser access'], ['pat', 'API token (PAT)']]) {
    if (value === 'portable' && !portableCredentialsEnabled) continue;
    const option = document.createElement('option');
    option.value = value;
    option.textContent = label;
    option.disabled = value === 'pat' && !policy;
    type.append(option);
  }
  host.append(field('Credential type', type));
  const patFields = document.createElement('div');
  const days = input('number', String(policy?.default_expiry_days || 90));
  days.min = String(policy?.min_expiry_days || 1);
  days.max = String(policy?.max_expiry_days || 365);
  days.step = '1';
  const scopeFields = document.createElement('fieldset');
  scopeFields.className = 'form-fieldset options-access-inline-card options-access-permissions';
  const legend = document.createElement('legend');
  legend.className = 'form-label';
  legend.textContent = 'Permissions';
  scopeFields.append(legend);
  const defaults = new Set(policy?.default_scopes || []);
  for (const scope of policy?.scopes || []) {
    const label = document.createElement('label');
    label.className = 'form-check';
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.name = 'pat_scope';
    checkbox.value = scope;
    checkbox.checked = defaults.has(scope);
    const text = document.createElement('span');
    text.textContent = SCOPE_LABELS[scope] || scope;
    label.append(checkbox, text);
    scopeFields.append(label);
  }
  const description = document.createElement('p');
  description.className = 'options-access-description';
  description.textContent = 'Use this token with the API or darklab CLI. Select only the permissions it needs. Team access also depends on your membership.';
  patFields.append(description, field('Expires in days', days), scopeFields);
  host.append(patFields);
  function syncType() {
    const pat = type.value === 'pat';
    patFields.hidden = !pat;
    expiryField.hidden = pat;
  }
  type.addEventListener('change', syncType);
  syncType();
  return {
    host,
    readOptions() {
      if (!policy && !portableCredentialsEnabled) throw new Error('API token settings could not be loaded. Refresh Access and try again.');
      if (type.value !== 'pat') {
        return { type: 'portable', expires_at: expiryInput.value ? new Date(expiryInput.value).toISOString() : null };
      }
      const lifetime = Number(days.value);
      if (!Number.isInteger(lifetime) || lifetime < Number(days.min) || lifetime > Number(days.max)) {
        throw new Error(`Choose an expiry between ${days.min} and ${days.max} days.`);
      }
      const scopes = [...scopeFields.querySelectorAll('input:checked')].map(checkbox => checkbox.value);
      if (!scopes.length) throw new Error('Select at least one permission for this API token.');
      return { type: 'pat', expires_in_days: lifetime, scopes };
    },
  };
}

export { buildCredentialCreationFields };
