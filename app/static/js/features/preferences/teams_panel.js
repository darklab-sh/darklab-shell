// Options modal team management.
(function initOptionsTeamsPanel(global) {
  let _teams = [];
  let _detail = null;
  let _selectedTeamId = '';
  let _loading = false;
  let _formMode = '';
  let _oneTimeCode = null;
  let _bound = false;

  const ROLES = Object.freeze(['owner', 'admin', 'operator', 'viewer']);

  function _el(id) {
    return document.getElementById(id);
  }

  function _apiFetch() {
    if (typeof apiFetch === 'function') return apiFetch;
    return typeof global.apiFetch === 'function' ? global.apiFetch.bind(global) : global.fetch.bind(global);
  }

  function _tokenSessionActive() {
    return typeof SESSION_ID !== 'undefined' && String(SESSION_ID || '').startsWith('tok_');
  }

  function _msg(text, { error = false } = {}) {
    const node = _el('options-teams-msg');
    if (!node) return;
    node.textContent = text || '';
    node.classList.toggle('is-error', !!error);
    node.style.display = text ? '' : 'none';
  }

  function _toast(text, tone = 'success') {
    _msg('');
    const toast = typeof showToast === 'function'
      ? showToast
      : (typeof global.showToast === 'function' ? global.showToast.bind(global) : null);
    if (toast) {
      toast(text, tone);
      return;
    }
    _msg(text, { error: tone === 'error' });
  }

  function _clipboardWriter() {
    if (typeof copyTextToClipboard === 'function') return copyTextToClipboard;
    if (typeof global.copyTextToClipboard === 'function') return global.copyTextToClipboard.bind(global);
    if (global.navigator?.clipboard && typeof global.navigator.clipboard.writeText === 'function') {
      return value => global.navigator.clipboard.writeText(value);
    }
    return null;
  }

  function _setBusy(busy) {
    _loading = !!busy;
    [
      'options-teams-refresh-btn',
      'options-team-create-btn',
      'options-team-join-btn',
      'options-team-recover-btn',
    ].forEach((id) => {
      const button = _el(id);
      if (button) button.disabled = _loading;
    });
    const panel = _el('options-panel-teams');
    if (panel) {
      panel.querySelectorAll('button, input, select').forEach((control) => {
        if (control.id && control.id.startsWith('options-team-')) return;
        control.disabled = _loading;
      });
    }
  }

  async function _jsonRequest(url, { method = 'GET', body = null } = {}) {
    const options = { method, cache: 'no-store' };
    if (body !== null) {
      options.headers = { 'Content-Type': 'application/json' };
      options.body = JSON.stringify(body);
    }
    const resp = await _apiFetch()(url, options);
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const message = data.message || data.error || `HTTP ${resp.status}`;
      throw new Error(message);
    }
    return data;
  }

  function _errorForLog(error, fallback = 'Team action failed') {
    if (error instanceof Error) return error;
    const message = String(error || fallback).trim() || fallback;
    return new Error(message);
  }

  function _logTeamClientError(event, action, error, context = {}) {
    const logError = typeof logClientError === 'function'
      ? logClientError
      : (typeof global.logClientError === 'function' ? global.logClientError.bind(global) : null);
    if (!logError) return;
    const teamId = String(context.team_id || context.teamId || _detail?.team?.id || _selectedTeamId || '');
    const payload = {
      action: String(action || 'unknown'),
      team_id: teamId,
    };
    if (context.target_member_id) payload.target_member_id = String(context.target_member_id);
    if (context.target_invite_id) payload.target_invite_id = String(context.target_invite_id);
    logError(`${event} ${JSON.stringify(payload)}`, _errorForLog(error));
  }

  function _logTeamActionFailure(action, error, context = {}) {
    _logTeamClientError('TEAM_ACTION_FAILED', action, error, context);
  }

  function _logTeamUiActionFailure(action, error, context = {}) {
    _logTeamClientError('TEAM_UI_ACTION_FAILED', action, error, context);
  }

  function _clear(node) {
    if (node) node.replaceChildren();
  }

  function _node(tag, className = '', text = '') {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function _button(label, action, { role = 'secondary', tone = '', compact = true } = {}) {
    const btn = document.createElement('button');
    btn.type = 'button';
    const classes = ['btn', `btn-${role}`];
    if (tone) classes.push(`btn-${tone}`);
    if (compact) classes.push('btn-compact');
    btn.className = classes.join(' ');
    btn.textContent = label;
    btn.dataset.teamAction = action;
    return btn;
  }

  function _field(label, input) {
    const wrap = _node('label', 'options-team-field');
    const labelNode = _node('span', 'options-team-field-label', label);
    wrap.append(labelNode, input);
    return wrap;
  }

  function _input(name, placeholder = '', value = '', { required = false, autocomplete = 'off' } = {}) {
    const input = document.createElement('input');
    input.className = 'form-control';
    input.name = name;
    input.type = 'text';
    input.autocomplete = autocomplete;
    input.autocapitalize = 'none';
    input.autocorrect = 'off';
    input.spellcheck = false;
    input.placeholder = placeholder;
    input.value = value || '';
    input.required = !!required;
    return input;
  }

  function _numberInput(name, value = '1') {
    const input = document.createElement('input');
    input.className = 'form-control';
    input.name = name;
    input.type = 'number';
    input.min = '1';
    input.max = '100';
    input.value = value;
    return input;
  }

  function _roleSelect(value = 'operator', { disabled = false } = {}) {
    const select = document.createElement('select');
    select.className = 'form-select';
    select.name = 'role';
    select.disabled = !!disabled;
    ROLES.forEach((role) => {
      const option = document.createElement('option');
      option.value = role;
      option.textContent = _titleize(role);
      select.appendChild(option);
    });
    select.value = ROLES.includes(value) ? value : 'operator';
    return select;
  }

  function _titleize(value) {
    return String(value || '')
      .replaceAll('_', ' ')
      .replace(/\b\w/g, char => char.toUpperCase());
  }

  function _formatDate(value) {
    const raw = String(value || '').trim();
    if (!raw) return '';
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return raw;
    return date.toLocaleString([], {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  function _actorRole() {
    return String(_detail?.team?.member?.role || '');
  }

  function _actorCapabilities() {
    const capabilities = _detail?.team?.member?.capabilities;
    return Array.isArray(capabilities) ? capabilities.map(item => String(item || '')) : [];
  }

  function _actorCan(capability) {
    return _actorCapabilities().includes(String(capability || ''));
  }

  function _activeTeamId() {
    if (typeof getActiveTeamId === 'function') return getActiveTeamId() || '';
    if (typeof global.getActiveTeamId === 'function') return global.getActiveTeamId() || '';
    return '';
  }

  async function _syncScopeSelector() {
    const replace = typeof replaceTeamScopes === 'function'
      ? replaceTeamScopes
      : (typeof global.replaceTeamScopes === 'function'
        ? global.replaceTeamScopes.bind(global)
        : (typeof global.DarklabTeamScope?.replaceTeamScopes === 'function'
          ? global.DarklabTeamScope.replaceTeamScopes
          : null));
    if (replace) replace({ teams: _teams });
  }

  function _renderOneTimeCode(parent, teamId = '') {
    if (!_oneTimeCode || (teamId && _oneTimeCode.teamId && _oneTimeCode.teamId !== teamId)) return;
    const panel = _node('div', 'options-team-panel');
    const title = _node('div', 'options-team-panel-title', _oneTimeCode.label || 'One-time code');
    const desc = _node('div', 'options-team-meta', 'Copy this now. It will not be shown again.');
    const code = _node('div', 'options-team-code');
    const codeText = document.createElement('code');
    codeText.textContent = _oneTimeCode.code || '';
    const copyBtn = _button('Copy', 'copy-code');
    copyBtn.dataset.codeValue = _oneTimeCode.code || '';
    code.append(codeText, copyBtn);
    panel.append(title, desc, code);
    parent.appendChild(panel);
  }

  function _renderTopForm() {
    const host = _el('options-team-form');
    _clear(host);
    if (!host || !_formMode) return;

    const form = document.createElement('form');
    form.className = 'options-team-panel';
    form.dataset.teamForm = _formMode;
    const titleMap = {
      create: 'Create team',
      join: 'Join team',
      recover: 'Use recovery code',
    };
    form.appendChild(_node('div', 'options-team-panel-title', titleMap[_formMode] || 'Team'));
    const fields = _node('div', 'options-team-fields');
    if (_formMode === 'create') {
      fields.append(
        _field('Team name', _input('name', 'Darklab ops', '', { required: true })),
        _field('Slug', _input('slug', 'darklab-ops')),
        _field('Your display name', _input('display_name', 'nona'))
      );
    } else {
      const codeLabel = _formMode === 'recover' ? 'Recovery code' : 'Invite code';
      fields.append(
        _field(codeLabel, _input('code', _formMode === 'recover' ? 'trec_...' : 'tinv_...', '', { required: true })),
        _field('Your display name', _input('display_name', 'nona'))
      );
    }
    const actions = _node('div', 'options-session-token-actions options-team-field-full');
    const submit = document.createElement('button');
    submit.type = 'submit';
    submit.className = 'btn btn-secondary btn-compact';
    submit.textContent = _formMode === 'create' ? 'Create' : 'Submit';
    actions.append(submit, _button('Cancel', 'cancel-form', { role: 'ghost' }));
    fields.appendChild(actions);
    form.appendChild(fields);
    host.appendChild(form);
  }

  function _teamRow(team) {
    const row = _node('div', 'options-team-row panel-row');
    const body = _node('div', 'options-team-row-body');
    const name = _node('div', 'options-team-name', team.name || team.slug || 'Team');
    const chips = _node('div', 'options-team-chips');
    const role = String(team.member?.role || team.role || '');
    const status = String(team.status || '');
    const active = _activeTeamId() === team.id;
    if (role) chips.appendChild(_node('span', 'badge badge-tone-blue options-team-chip', _titleize(role)));
    if (status) chips.appendChild(_node('span', `badge ${status === 'active' ? 'badge-tone-green' : 'badge-tone-muted'} options-team-chip`, _titleize(status)));
    if (active) chips.appendChild(_node('span', 'badge badge-tone-green options-team-chip', 'Active scope'));
    const metaParts = [];
    if (team.slug) metaParts.push(team.slug);
    if (team.updated_at) metaParts.push(`updated ${_formatDate(team.updated_at)}`);
    const meta = _node('div', 'options-team-meta', metaParts.join(' · '));
    body.append(name, chips, meta);
    const actions = _node('div', 'options-team-actions');
    const manage = _button('Manage', 'select-team');
    manage.dataset.teamId = team.id;
    const switchBtn = _button(active ? 'Active' : 'Switch', 'switch-team');
    switchBtn.dataset.teamId = team.id;
    switchBtn.disabled = active || status === 'archived';
    actions.append(manage, switchBtn);
    row.append(body, actions);
    return row;
  }

  function _personalScopeRow() {
    const active = !_activeTeamId();
    const row = _node('div', 'options-team-row panel-row');
    const body = _node('div', 'options-team-row-body');
    const name = _node('div', 'options-team-name', 'Personal');
    const chips = _node('div', 'options-team-chips');
    chips.appendChild(_node('span', 'badge badge-tone-muted options-team-chip', 'Private scope'));
    if (active) chips.appendChild(_node('span', 'badge badge-tone-green options-team-chip', 'Active scope'));
    const meta = _node('div', 'options-team-meta', 'Your personal runs, files, projects, secrets, and history.');
    body.append(name, chips, meta);
    const actions = _node('div', 'options-team-actions');
    const switchBtn = _button(active ? 'Active' : 'Switch', 'switch-personal');
    switchBtn.disabled = active;
    actions.appendChild(switchBtn);
    row.append(body, actions);
    return row;
  }

  function _renderList() {
    const list = _el('options-teams-list');
    _clear(list);
    if (!list) return;
    if (!_tokenSessionActive()) {
      const empty = _node('div', 'options-team-empty-state');
      empty.append(
        _node('div', 'options-team-empty', 'Teams require a session token. Generate or set one on the Preferences tab first.')
      );
      list.appendChild(empty);
      return;
    }
    if (_loading && !_teams.length) {
      list.appendChild(_node('div', 'options-team-empty', 'Loading teams...'));
      return;
    }
    list.appendChild(_personalScopeRow());
    if (!_teams.length) {
      list.appendChild(_node('div', 'options-team-empty', 'No teams yet.'));
      return;
    }
    _teams.forEach(team => list.appendChild(_teamRow(team)));
  }

  function _renderMembers(section) {
    const title = _node('div', 'options-team-section-title', 'Members');
    section.appendChild(title);
    const members = Array.isArray(_detail?.members) ? _detail.members : [];
    if (!members.length) {
      section.appendChild(_node('div', 'options-team-empty', 'No members.'));
      return;
    }
    const activeOwnerCount = members.filter(member =>
      member
      && member.role === 'owner'
      && member.status === 'active'
      && !member.removed_at
    ).length;
    members.forEach((member) => {
      const removed = !!member.removed_at || member.status !== 'active';
      const canManageOwner = _actorCan('manage_owners');
      const canManageMember = _actorCan('manage_members');
      const isOnlyCurrentOwner = member.is_current && member.role === 'owner' && activeOwnerCount <= 1;
      const canEditRole = !removed
        && !isOnlyCurrentOwner
        && (member.role === 'owner' ? canManageOwner : canManageMember);
      const canEdit = !removed && (member.is_current || canEditRole);
      const row = _node('div', `options-team-member-row panel-row${removed ? ' is-removed' : ''}`);
      const form = document.createElement('form');
      form.className = 'options-team-member-form';
      form.dataset.memberId = member.id || '';
      const main = _node('div', 'options-team-row-main');
      const name = _node('div', 'options-team-name', member.display_name || (member.is_current ? 'You' : member.id || 'member'));
      const metaParts = [];
      if (member.is_current) metaParts.push('current token');
      if (member.joined_at) metaParts.push(`joined ${_formatDate(member.joined_at)}`);
      if (removed) metaParts.push('removed');
      main.append(name, _node('div', 'options-team-meta', metaParts.join(' · ')));
      const roleSelect = _roleSelect(member.role || 'operator', { disabled: !canEditRole });
      if (isOnlyCurrentOwner) {
        roleSelect.title = 'Promote another owner before changing your role.';
      }
      const actions = _node('div', 'options-team-row-actions');
      const displayInput = _input('display_name', 'Display name', member.display_name || '');
      displayInput.disabled = !canEdit;
      displayInput.classList.add('options-team-field-full');
      if (canEdit) {
        const save = document.createElement('button');
        save.type = 'submit';
        save.className = 'btn btn-secondary btn-compact';
        save.textContent = 'Save';
        actions.appendChild(save);
      }
      if (!removed && !member.is_current && canEditRole) {
        const remove = _button('Remove', 'remove-member', { role: 'destructive' });
        remove.dataset.memberId = member.id || '';
        actions.appendChild(remove);
      }
      form.append(main, roleSelect, actions, displayInput);
      row.appendChild(form);
      section.appendChild(row);
    });
  }

  function _inviteStatus(invite) {
    if (invite.revoked_at) return 'revoked';
    if (invite.max_uses && invite.use_count >= invite.max_uses) return 'used';
    if (invite.expires_at) {
      const expires = new Date(invite.expires_at);
      if (!Number.isNaN(expires.getTime()) && expires.getTime() < Date.now()) return 'expired';
    }
    return 'active';
  }

  function _renderInvites(section) {
    const canInvite = _actorCan('manage_invites');
    const header = _node('div', 'options-team-section-title', 'Invites');
    section.appendChild(header);
    if (canInvite) {
      const form = document.createElement('form');
      form.className = 'options-team-panel';
      form.dataset.teamInviteForm = 'create';
      const fields = _node('div', 'options-team-fields');
      fields.append(
        _field('Role', _roleSelect('operator')),
        _field('Label', _input('label', 'Alice laptop')),
        _field('Max uses', _numberInput('max_uses', '1'))
      );
      const actions = _node('div', 'options-session-token-actions options-team-field-full');
      const submit = document.createElement('button');
      submit.type = 'submit';
      submit.className = 'btn btn-secondary btn-compact';
      submit.textContent = 'Create invite';
      actions.appendChild(submit);
      fields.appendChild(actions);
      form.appendChild(fields);
      section.appendChild(form);
    }
    const invites = Array.isArray(_detail?.invites) ? _detail.invites : [];
    if (!invites.length) {
      section.appendChild(_node('div', 'options-team-empty', 'No invites.'));
      return;
    }
    invites.forEach((invite) => {
      const status = _inviteStatus(invite);
      const row = _node('div', `options-team-invite-row panel-row${status !== 'active' ? ' is-revoked' : ''}`);
      const main = _node('div', 'options-team-row-main');
      main.append(
        _node('div', 'options-team-name', invite.label || invite.id || 'invite'),
        _node('div', 'options-team-meta', `${_titleize(invite.role)} · ${invite.use_count || 0}/${invite.max_uses || 0} uses · ${_titleize(status)}`)
      );
      const created = _node('div', 'options-team-meta', invite.created_at ? _formatDate(invite.created_at) : '');
      const actions = _node('div', 'options-team-row-actions');
      if (canInvite && status === 'active') {
        const revoke = _button('Revoke', 'revoke-invite', { role: 'destructive' });
        revoke.dataset.inviteId = invite.id || '';
        actions.appendChild(revoke);
      }
      row.append(main, created, actions);
      section.appendChild(row);
    });
  }

  function _renderRecovery(section) {
    const canRecovery = _actorCan('manage_recovery');
    const header = _node('div', 'options-team-section-title', 'Recovery');
    section.appendChild(header);
    const actions = _node('div', 'options-session-token-actions');
    const rotate = _button('Rotate recovery code', 'rotate-recovery');
    rotate.disabled = !canRecovery;
    actions.appendChild(rotate);
    section.appendChild(actions);
    const rows = Array.isArray(_detail?.recovery_codes) ? _detail.recovery_codes : [];
    if (!rows.length) {
      section.appendChild(_node('div', 'options-team-empty', 'No recovery codes.'));
      return;
    }
    rows.slice(0, 5).forEach((recovery) => {
      const inactive = !!(recovery.revoked_at || recovery.used_at || recovery.rotated_at);
      const row = _node('div', `options-team-recovery-row panel-row${inactive ? ' is-inactive' : ''}`);
      const main = _node('div', 'options-team-row-main');
      main.append(
        _node('div', 'options-team-name', inactive ? 'Inactive recovery code' : 'Active recovery code'),
        _node('div', 'options-team-meta', recovery.created_at ? `created ${_formatDate(recovery.created_at)}` : '')
      );
      row.append(main, _node('div', 'options-team-meta', inactive ? 'inactive' : 'active'), _node('div', 'options-team-row-actions'));
      section.appendChild(row);
    });
  }

  function _renderDetail() {
    const host = _el('options-team-detail');
    _clear(host);
    if (!host) return;
    if (!_selectedTeamId) return;
    if (!_detail) {
      host.appendChild(_node('div', 'options-team-empty', 'Loading team...'));
      return;
    }
    const team = _detail.team || {};
    const actorRole = _actorRole();
    const panel = _node('div', 'options-team-panel options-team-sections');
    const header = _node('div', 'options-team-row panel-row');
    const body = _node('div', 'options-team-row-body');
    body.append(
      _node('div', 'options-team-name', team.name || team.slug || 'Team'),
      _node('div', 'options-team-meta', `${team.slug || team.id || ''} · ${_titleize(team.status || 'active')} · ${_titleize(actorRole || 'member')}`)
    );
    const actions = _node('div', 'options-team-actions');
    const switchBtn = _button(_activeTeamId() === team.id ? 'Active scope' : 'Switch scope', 'switch-team');
    switchBtn.dataset.teamId = team.id || '';
    switchBtn.disabled = _activeTeamId() === team.id || team.status === 'archived';
    actions.appendChild(switchBtn);
    if (_actorCan('archive_team')) {
      const archive = _button(
        team.status === 'archived' ? 'Reactivate' : 'Archive',
        team.status === 'archived' ? 'reactivate-team' : 'archive-team'
      );
      archive.dataset.teamId = team.id || '';
      actions.appendChild(archive);
    }
    const leave = _button('Leave', 'leave-team', { role: 'destructive' });
    leave.dataset.teamId = team.id || '';
    actions.appendChild(leave);
    header.append(body, actions);
    panel.appendChild(header);
    if (team.status === 'archived') {
      panel.appendChild(_node(
        'div',
        'options-team-empty',
        'Archived teams keep schedules and watchers paused. Reactivating restores access, but automation stays paused until it is resumed.'
      ));
    }
    _renderOneTimeCode(panel, team.id);

    const members = _node('div', 'options-team-section');
    _renderMembers(members);
    panel.appendChild(members);

    const invites = _node('div', 'options-team-section');
    _renderInvites(invites);
    panel.appendChild(invites);

    const recovery = _node('div', 'options-team-section');
    _renderRecovery(recovery);
    panel.appendChild(recovery);

    host.appendChild(panel);
    const enhanceSelects = typeof enhanceAppSelects === 'function'
      ? enhanceAppSelects
      : (typeof global.enhanceAppSelects === 'function' ? global.enhanceAppSelects.bind(global) : null);
    if (enhanceSelects) {
      host.querySelectorAll('select.form-select').forEach((select) => { select.dataset.portalMenu = 'true'; });
      enhanceSelects(host);
    }
  }

  function _render() {
    _renderTopForm();
    _renderList();
    _renderDetail();
  }

  async function refreshOptionsTeams() {
    const list = _el('options-teams-list');
    if (!list) return [];
    if (!_tokenSessionActive()) {
      _teams = [];
      _detail = null;
      _selectedTeamId = '';
      _render();
      _syncScopeSelector();
      return _teams;
    }
    _setBusy(true);
    try {
      const payload = await _jsonRequest('/session/teams');
      _teams = Array.isArray(payload.teams) ? payload.teams : [];
      if (_selectedTeamId && !_teams.some(team => team.id === _selectedTeamId)) {
        _selectedTeamId = '';
        _detail = null;
      }
      _render();
      _syncScopeSelector();
      return _teams;
    } catch (error) {
      _logTeamActionFailure('list_teams', error);
      _msg(error.message || 'Failed to load teams', { error: true });
      return [];
    } finally {
      _setBusy(false);
      _render();
    }
  }

  async function _loadTeamDetail(teamId) {
    const normalized = String(teamId || '').trim();
    if (!normalized) return;
    _selectedTeamId = normalized;
    _detail = null;
    _renderDetail();
    _setBusy(true);
    try {
      _detail = await _jsonRequest(`/session/teams/${encodeURIComponent(normalized)}`);
      _render();
    } catch (error) {
      _logTeamActionFailure('load_team', error, { team_id: normalized });
      _msg(error.message || 'Failed to load team', { error: true });
    } finally {
      _setBusy(false);
      _render();
    }
  }

  async function _confirm(body, { tone = 'warning', confirmLabel = 'Continue', destructive = false } = {}) {
    const confirmModal = typeof showConfirm === 'function'
      ? showConfirm
      : (typeof global.showConfirm === 'function' ? global.showConfirm.bind(global) : null);
    if (confirmModal) {
      const choice = await confirmModal({
        body,
        tone,
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'confirm', label: confirmLabel, role: destructive ? 'destructive' : null, tone },
        ],
      });
      return choice === 'confirm';
    }
    return typeof global.confirm === 'function'
      ? global.confirm(typeof body === 'string' ? body : body.text || confirmLabel)
      : false;
  }

  async function _submitTopForm(form) {
    const data = Object.fromEntries(new FormData(form).entries());
    const mode = form.dataset.teamForm;
    _setBusy(true);
    try {
      if (mode === 'create') {
        const payload = {
          name: String(data.name || ''),
          slug: String(data.slug || ''),
          display_name: String(data.display_name || ''),
        };
        const response = await _jsonRequest('/session/teams', { method: 'POST', body: payload });
        _formMode = '';
        _oneTimeCode = { teamId: response.team?.id || '', label: 'Recovery code', code: response.recovery_code || '' };
        await refreshOptionsTeams();
        await _loadTeamDetail(response.team?.id || '');
        _toast('Team created');
        return;
      }
      const url = mode === 'recover' ? '/session/teams/recovery/redeem' : '/session/teams/join';
      const response = await _jsonRequest(url, {
        method: 'POST',
        body: {
          code: String(data.code || ''),
          display_name: String(data.display_name || ''),
        },
      });
      _formMode = '';
      _oneTimeCode = null;
      await refreshOptionsTeams();
      await _loadTeamDetail(response.team?.id || '');
      _toast(mode === 'recover' ? 'Recovery code redeemed' : 'Team joined');
    } catch (error) {
      const action = mode === 'create'
        ? 'create_team'
        : (mode === 'recover' ? 'redeem_recovery_code' : 'join_team');
      _logTeamActionFailure(action, error);
      _msg(error.message || 'Team action failed', { error: true });
    } finally {
      _setBusy(false);
      _render();
    }
  }

  async function _createInvite(form) {
    if (!_detail?.team?.id) return;
    const data = Object.fromEntries(new FormData(form).entries());
    _setBusy(true);
    try {
      const response = await _jsonRequest(`/session/teams/${encodeURIComponent(_detail.team.id)}/invites`, {
        method: 'POST',
        body: {
          role: String(data.role || 'operator'),
          label: String(data.label || ''),
          max_uses: Number.parseInt(String(data.max_uses || '1'), 10) || 1,
        },
      });
      _oneTimeCode = { teamId: _detail.team.id, label: 'Invite code', code: response.invite?.code || '' };
      await _loadTeamDetail(_detail.team.id);
      _toast('Invite created');
    } catch (error) {
      _logTeamActionFailure('create_invite', error, { team_id: _detail.team.id });
      _msg(error.message || 'Failed to create invite', { error: true });
    } finally {
      _setBusy(false);
      _render();
    }
  }

  async function _updateMember(form) {
    if (!_detail?.team?.id) return;
    const memberId = form.dataset.memberId || '';
    if (!memberId) return;
    const displayInput = form.querySelector('[name="display_name"]');
    const roleSelect = form.querySelector('[name="role"]');
    const body = { display_name: displayInput ? displayInput.value : '' };
    if (roleSelect && !roleSelect.disabled) body.role = roleSelect.value;
    _setBusy(true);
    try {
      await _jsonRequest(`/session/teams/${encodeURIComponent(_detail.team.id)}/members/${encodeURIComponent(memberId)}`, {
        method: 'PATCH',
        body,
      });
      await _loadTeamDetail(_detail.team.id);
      _toast('Member updated');
    } catch (error) {
      _logTeamActionFailure('update_member', error, {
        team_id: _detail.team.id,
        target_member_id: memberId,
      });
      _msg(error.message || 'Failed to update member', { error: true });
    } finally {
      _setBusy(false);
      _render();
    }
  }

  async function _handleListAction(action, target) {
    const teamId = target.dataset.teamId || '';
    if (action === 'select-team') {
      await _loadTeamDetail(teamId);
    } else if (action === 'switch-personal') {
      const setScope = typeof setActiveTeamId === 'function'
        ? setActiveTeamId
        : (typeof global.setActiveTeamId === 'function' ? global.setActiveTeamId.bind(global) : null);
      if (setScope && setScope('')) {
        _toast('Personal scope selected');
        _render();
      }
    } else if (action === 'switch-team') {
      const setScope = typeof setActiveTeamId === 'function'
        ? setActiveTeamId
        : (typeof global.setActiveTeamId === 'function' ? global.setActiveTeamId.bind(global) : null);
      if (setScope && setScope(teamId)) {
        _toast('Team scope selected');
        _render();
      }
    }
  }

  async function _handleDetailAction(action, target) {
    const teamId = _detail?.team?.id || target.dataset.teamId || '';
    if (!teamId && action !== 'copy-code') return;
    if (action === 'copy-code') {
      const code = target.dataset.codeValue || _oneTimeCode?.code || '';
      const copyText = _clipboardWriter();
      if (!code || !copyText) {
        _toast('Code is no longer available', 'error');
        return;
      }
      try {
        await copyText(code);
        _toast('Code copied');
      } catch (_) {
        _toast('Failed to copy code', 'error');
      }
      return;
    }
    if (action === 'switch-team') {
      const setScope = typeof setActiveTeamId === 'function'
        ? setActiveTeamId
        : (typeof global.setActiveTeamId === 'function' ? global.setActiveTeamId.bind(global) : null);
      if (setScope && setScope(teamId)) {
        _toast('Team scope selected');
        _render();
      }
      return;
    }
    if (action === 'rotate-recovery') {
      const ok = await _confirm({
        text: 'Rotate this team recovery code?',
        note: 'Existing unused recovery codes stop working.',
      }, { tone: 'warning', confirmLabel: 'Rotate' });
      if (!ok) return;
      _setBusy(true);
      try {
        const response = await _jsonRequest(`/session/teams/${encodeURIComponent(teamId)}/recovery/rotate`, { method: 'POST', body: {} });
        _oneTimeCode = { teamId, label: 'Recovery code', code: response.recovery_code || '' };
        await _loadTeamDetail(teamId);
        _toast('Recovery code rotated');
      } catch (error) {
        _logTeamActionFailure('rotate_recovery_code', error, { team_id: teamId });
        _msg(error.message || 'Failed to rotate recovery code', { error: true });
      } finally {
        _setBusy(false);
      }
      return;
    }
    if (action === 'archive-team' || action === 'reactivate-team') {
      const status = action === 'archive-team' ? 'archived' : 'active';
      const ok = await _confirm({
        text: `${status === 'archived' ? 'Archive' : 'Reactivate'} this team?`,
        note: status === 'archived'
          ? 'Team schedules and watchers pause while the team is archived.'
          : 'Team members can use this team again, but schedules and watchers paused by archival stay paused until you resume them.',
      }, { tone: status === 'archived' ? 'warning' : null, confirmLabel: status === 'archived' ? 'Archive' : 'Reactivate' });
      if (!ok) return;
      _setBusy(true);
      try {
        await _jsonRequest(`/session/teams/${encodeURIComponent(teamId)}`, { method: 'PATCH', body: { status } });
        await refreshOptionsTeams();
        await _loadTeamDetail(teamId);
        _toast(status === 'archived' ? 'Team archived' : 'Team reactivated; schedules and watchers remain paused');
      } catch (error) {
        _logTeamActionFailure(status === 'archived' ? 'archive_team' : 'reactivate_team', error, { team_id: teamId });
        _msg(error.message || 'Failed to update team', { error: true });
      } finally {
        _setBusy(false);
      }
      return;
    }
    if (action === 'leave-team') {
      const ok = await _confirm({
        text: 'Leave this team?',
        note: 'Shared team data stays with the team.',
      }, { tone: 'danger', confirmLabel: 'Leave team', destructive: true });
      if (!ok) return;
      _setBusy(true);
      try {
        await _jsonRequest(`/session/teams/${encodeURIComponent(teamId)}/leave`, { method: 'POST', body: {} });
        _selectedTeamId = '';
        _detail = null;
        _oneTimeCode = null;
        await refreshOptionsTeams();
        _toast('Left team');
      } catch (error) {
        _logTeamActionFailure('leave_team', error, { team_id: teamId });
        _msg(error.message || 'Failed to leave team', { error: true });
      } finally {
        _setBusy(false);
      }
      return;
    }
    if (action === 'revoke-invite') {
      const inviteId = target.dataset.inviteId || '';
      if (!inviteId) return;
      const ok = await _confirm('Revoke this invite?', { tone: 'warning', confirmLabel: 'Revoke' });
      if (!ok) return;
      _setBusy(true);
      try {
        await _jsonRequest(`/session/teams/${encodeURIComponent(teamId)}/invites/${encodeURIComponent(inviteId)}`, { method: 'DELETE' });
        await _loadTeamDetail(teamId);
        _toast('Invite revoked');
      } catch (error) {
        _logTeamActionFailure('revoke_invite', error, {
          team_id: teamId,
          target_invite_id: inviteId,
        });
        _msg(error.message || 'Failed to revoke invite', { error: true });
      } finally {
        _setBusy(false);
      }
      return;
    }
    if (action === 'remove-member') {
      const memberId = target.dataset.memberId || '';
      if (!memberId) return;
      const ok = await _confirm('Remove this member from the team?', { tone: 'danger', confirmLabel: 'Remove', destructive: true });
      if (!ok) return;
      _setBusy(true);
      try {
        await _jsonRequest(`/session/teams/${encodeURIComponent(teamId)}/members/${encodeURIComponent(memberId)}`, { method: 'DELETE' });
        await _loadTeamDetail(teamId);
        _toast('Member removed');
      } catch (error) {
        _logTeamActionFailure('remove_member', error, {
          team_id: teamId,
          target_member_id: memberId,
        });
        _msg(error.message || 'Failed to remove member', { error: true });
      } finally {
        _setBusy(false);
      }
    }
  }

  function _bind() {
    if (_bound) return;
    _bound = true;
    _el('options-teams-refresh-btn')?.addEventListener('click', () => {
      refreshOptionsTeams().catch(error => _logTeamUiActionFailure('refresh_teams', error));
    });
    _el('options-team-create-btn')?.addEventListener('click', () => {
      _formMode = _formMode === 'create' ? '' : 'create';
      _renderTopForm();
    });
    _el('options-team-join-btn')?.addEventListener('click', () => {
      _formMode = _formMode === 'join' ? '' : 'join';
      _renderTopForm();
    });
    _el('options-team-recover-btn')?.addEventListener('click', () => {
      _formMode = _formMode === 'recover' ? '' : 'recover';
      _renderTopForm();
    });
    _el('options-team-form')?.addEventListener('submit', (event) => {
      event.preventDefault();
      const mode = event.target.dataset.teamForm || 'unknown';
      const action = mode === 'create'
        ? 'create_team'
        : (mode === 'recover' ? 'redeem_recovery_code' : 'join_team');
      _submitTopForm(event.target).catch(error => _logTeamUiActionFailure(action, error));
    });
    _el('options-team-form')?.addEventListener('click', (event) => {
      const action = event.target.closest('[data-team-action]')?.dataset.teamAction;
      if (action === 'cancel-form') {
        _formMode = '';
        _renderTopForm();
      }
    });
    _el('options-teams-list')?.addEventListener('click', (event) => {
      const target = event.target.closest('[data-team-action]');
      if (!target) return;
      _handleListAction(target.dataset.teamAction, target).catch(error => _logTeamUiActionFailure(
        target.dataset.teamAction,
        error,
        { team_id: target.dataset.teamId || '' }
      ));
    });
    _el('options-team-detail')?.addEventListener('click', (event) => {
      const target = event.target.closest('[data-team-action]');
      if (!target) return;
      _handleDetailAction(target.dataset.teamAction, target).catch(error => _logTeamUiActionFailure(
        target.dataset.teamAction,
        error,
        {
          team_id: target.dataset.teamId || _detail?.team?.id || '',
          target_invite_id: target.dataset.inviteId || '',
          target_member_id: target.dataset.memberId || '',
        }
      ));
    });
    _el('options-team-detail')?.addEventListener('submit', (event) => {
      event.preventDefault();
      const form = event.target;
      if (form.dataset.teamInviteForm) {
        _createInvite(form).catch(error => _logTeamUiActionFailure('create_invite', error, {
          team_id: _detail?.team?.id || '',
        }));
      } else if (form.dataset.memberId) {
        _updateMember(form).catch(error => _logTeamUiActionFailure('update_member', error, {
          team_id: _detail?.team?.id || '',
          target_member_id: form.dataset.memberId || '',
        }));
      }
    });
  }

  _bind();
  global.refreshOptionsTeams = refreshOptionsTeams;
})(window);
