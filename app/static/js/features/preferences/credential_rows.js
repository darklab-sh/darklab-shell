// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

function credentialState(credential, now = Date.now()) {
  if (credential?.revoked_at) return 'Revoked';
  const expires = credential?.expires_at ? Date.parse(credential.expires_at) : Number.NaN;
  if (Number.isFinite(expires) && expires <= now) return 'Expired';
  return 'Active';
}

function formatCredentialDate(value, fallback = 'Never') {
  if (!value) return fallback;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return fallback;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(parsed);
}

function _node(tag, className = '', text = '') {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function _action(label, action, credential, onAction, tone = '') {
  const button = _node('button', `btn btn-${tone || 'ghost'} btn-compact`, label);
  button.type = 'button';
  button.dataset.credentialAction = action;
  button.addEventListener('click', () => onAction(action, credential, button));
  return button;
}

function renderCredentialRows(host, credentials, { currentCredentialId = '', onAction = () => {} } = {}) {
  host.replaceChildren();
  if (!credentials.length) {
    host.append(_node('div', 'options-access-empty', 'No credentials have been issued yet.'));
    return;
  }
  credentials.forEach((credential) => {
    const state = credentialState(credential);
    const current = credential.id === currentCredentialId;
    const row = _node('article', 'panel-row options-access-row');
    row.dataset.credentialId = credential.id;
    const main = _node('div', 'options-access-row-main');
    const heading = _node('div', 'options-access-row-heading');
    heading.append(_node('strong', 'options-access-row-label', credential.label || 'Unlabeled credential'));
    if (current) heading.append(_node('span', 'badge badge-tone-green', 'Current'));
    heading.append(_node('span', `badge ${state === 'Active' ? 'badge-tone-green' : 'badge-tone-red'}`, state));
    const prefix = _node('code', 'options-access-prefix', credential.public_prefix || credential.id || '');
    const kind = credential.credential_type === 'pat' ? 'Personal access token' : 'Access credential';
    const facts = _node('div', 'options-access-row-facts');
    facts.append(
      _node('span', '', kind),
      _node('span', '', `Created ${formatCredentialDate(credential.created_at, 'Unknown')}`),
      _node('span', '', `Last used ${formatCredentialDate(credential.last_used_at)}`),
      _node('span', '', credential.expires_at ? `Expires ${formatCredentialDate(credential.expires_at)}` : 'No expiry'),
    );
    main.append(heading, prefix, facts);
    row.append(main);
    if (state === 'Active') {
      const actions = _node('div', 'options-access-row-actions');
      actions.append(
        _action('Rename', 'rename', credential, onAction),
        _action('Expiry', 'expiry', credential, onAction),
        _action('Rotate', 'rotate', credential, onAction),
        _action('Revoke', 'revoke', credential, onAction, 'secondary btn-warning'),
      );
      row.append(actions);
    }
    host.append(row);
  });
}

export { credentialState, formatCredentialDate, renderCredentialRows };
