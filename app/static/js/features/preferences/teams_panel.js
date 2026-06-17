// Options modal team management.
import {
  copyTextToClipboard as importedCopyTextToClipboard,
  showToast as importedShowToast,
} from '../../core/utils.js';
import { showConfirm as importedShowConfirm } from '../../ui/ui_confirm.js';
import { bindDisclosure as importedBindDisclosure } from '../../ui/ui_disclosure.js';
import { enhanceAppSelects as importedEnhanceAppSelects } from '../../ui/ui_helpers.js';
import {
  apiFetch as importedApiFetch,
  getSessionId as importedGetSessionId,
  logClientError as importedLogClientError,
} from '../../runtime_bridge.js';

let exportedRefreshOptionsTeams = null;

(function initOptionsTeamsPanel(global) {
  let _teams = [];
  let _detail = null;
  let _selectedTeamId = '';
  let _activeDetailTab = 'overview';
  let _loading = false;
  let _formMode = '';
  let _oneTimeCode = null;
  let _bound = false;
  const _activityStates = new Map();
  const _recentActivityStates = new Map();

  const ROLES = Object.freeze(['owner', 'admin', 'operator', 'viewer']);
  const TEAM_ACTIVITY_TARGET_TYPES = Object.freeze([
    ['', 'All targets'],
    ['team', 'Team'],
    ['project', 'Project'],
    ['finding', 'Finding'],
    ['target', 'Target'],
    ['run', 'Run'],
    ['package', 'Package'],
    ['report', 'Report'],
    ['file', 'File'],
    ['import', 'Import'],
    ['notification', 'Notification'],
    ['schedule', 'Schedule'],
    ['watcher', 'Watcher'],
    ['secret', 'Secret'],
  ]);

  function _el(id) {
    return document.getElementById(id);
  }

  function _apiFetch() {
    return typeof importedApiFetch === 'function' ? importedApiFetch : global.fetch.bind(global);
  }

  function _tokenSessionActive() {
    return String(typeof importedGetSessionId === 'function' ? importedGetSessionId() : '').startsWith('tok_');
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
    const toast = (typeof importedShowToast !== 'undefined' && importedShowToast)
      || null;
    if (toast) {
      toast(text, tone);
      return;
    }
    _msg(text, { error: tone === 'error' });
  }

  function _clipboardWriter() {
    if (typeof importedCopyTextToClipboard !== 'undefined' && importedCopyTextToClipboard) {
      return importedCopyTextToClipboard;
    }
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
    const logError = typeof importedLogClientError === 'function' ? importedLogClientError : null;
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

  function _input(name, placeholder = '', value = '', { required = false, autocomplete = 'off', type = 'text' } = {}) {
    const input = document.createElement('input');
    input.className = 'form-control';
    input.name = name;
    input.type = type;
    input.autocomplete = autocomplete;
    input.autocapitalize = 'none';
    input.autocorrect = 'off';
    input.spellcheck = false;
    input.placeholder = placeholder;
    input.value = value || '';
    input.required = !!required;
    return input;
  }

  function _formValues(form) {
    const values = {};
    form?.querySelectorAll?.('input[name], select[name], textarea[name]').forEach((field) => {
      values[field.name] = field.value;
    });
    return values;
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

  function _select(name, options, value = '') {
    const select = document.createElement('select');
    select.className = 'form-select';
    select.name = name;
    options.forEach(([optionValue, label]) => {
      const option = document.createElement('option');
      option.value = optionValue;
      option.textContent = label;
      select.appendChild(option);
    });
    select.value = value || '';
    return select;
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
      .replaceAll('.', ' ')
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

  function _canViewTeamActivity() {
    return ['owner', 'admin'].includes(_actorRole());
  }

  function _activityState(teamId) {
    const id = String(teamId || '');
    if (!_activityStates.has(id)) {
      _activityStates.set(id, {
        error: '',
        events: [],
        filters: {
          event_type: '',
          actor: '',
          target_type: '',
          target_id: '',
          date_from: '',
          date_to: '',
        },
        hasMore: false,
        limit: 25,
        loaded: false,
        loading: false,
        offset: 0,
        retentionDays: 0,
      });
    }
    return _activityStates.get(id);
  }

  function _recentActivityState(teamId) {
    const id = String(teamId || '');
    if (!_recentActivityStates.has(id)) {
      _recentActivityStates.set(id, {
        error: '',
        events: [],
        hasMore: false,
        loaded: false,
        loading: false,
      });
    }
    return _recentActivityStates.get(id);
  }

  function _hasActivityFilters(st) {
    return Object.values(st?.filters || {}).some(value => String(value || '').trim());
  }

  function _activityParams(st) {
    const params = new URLSearchParams();
    Object.entries(st.filters || {}).forEach(([key, value]) => {
      const normalized = String(value || '').trim();
      if (normalized) params.set(key, normalized);
    });
    params.set('limit', String(st.limit));
    params.set('offset', String(st.offset));
    return params;
  }

  function _readActivityFilters(root, st) {
    if (!root || !st) return;
    root.querySelectorAll('[data-team-activity-filter]').forEach((control) => {
      st.filters[control.dataset.teamActivityFilter] = String(control.value || '').trim();
    });
  }

  function _resetActivityFilters(st) {
    if (!st) return;
    Object.keys(st.filters).forEach((key) => { st.filters[key] = ''; });
  }

  function _activeTeamId() {
    return global.DarklabTeamScope?.getActiveTeamId?.() || '';
  }

  function _setActiveTeamScope(teamId, options = {}) {
    const setScope = global.DarklabTeamScope?.setActiveTeamId;
    return typeof setScope === 'function' ? setScope(teamId, options) : false;
  }

  async function _syncScopeSelector() {
    const replace = global.DarklabTeamScope?.replaceTeamScopes;
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
    const existingForm = host?.querySelector?.('[data-team-form]');
    const existingMode = existingForm?.dataset?.teamForm || '';
    const existingValues = existingMode === _formMode && existingForm
      ? _formValues(existingForm)
      : {};
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
        _field('Team name', _input('name', 'Darklab ops', existingValues.name || '', { required: true })),
        _field('Slug', _input('slug', 'darklab-ops', existingValues.slug || '')),
        _field('Your display name', _input('display_name', 'nona', existingValues.display_name || ''))
      );
    } else {
      const codeLabel = _formMode === 'recover' ? 'Recovery code' : 'Invite code';
      fields.append(
        _field(codeLabel, _input('code', _formMode === 'recover' ? 'trec_...' : 'tinv_...', existingValues.code || '', { required: true })),
        _field('Your display name', _input('display_name', 'nona', existingValues.display_name || ''))
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

  function _activityActorLabel(event) {
    const actor = event?.actor && typeof event.actor === 'object' ? event.actor : {};
    const name = String(actor.display_name || actor.member_id || '').trim();
    const role = String(actor.role || '').trim();
    if (name && role) return `${name} · ${role}`;
    return name || role || 'System';
  }

  function _activityTargetLabel(event) {
    const target = event?.target && typeof event.target === 'object' ? event.target : {};
    const type = String(target.type || '').trim();
    const id = String(target.id || '').trim();
    if (type && id) return `${type}:${id}`;
    return id || type || 'team';
  }

  function _activitySummary(details) {
    const value = details && typeof details === 'object' ? details : {};
    const parts = [];
    Object.entries(value).some(([key, item]) => {
      if (item && typeof item === 'object') return false;
      if (item === undefined || item === null || item === '') return false;
      parts.push(`${key.replaceAll('_', ' ')}: ${String(item)}`);
      return parts.length >= 3;
    });
    return parts.join(' · ') || 'Recorded activity';
  }

  function _activityDetailValue(value) {
    if (Array.isArray(value)) {
      const items = value
        .filter(item => item !== undefined && item !== null && item !== '')
        .map(item => (item && typeof item === 'object' ? '[object]' : String(item)));
      return items.length ? items.join(', ') : 'none';
    }
    if (value && typeof value === 'object') {
      const parts = Object.entries(value)
        .filter(([, item]) => item !== undefined && item !== null && item !== '')
        .slice(0, 4)
        .map(([key, item]) => `${key.replaceAll('_', ' ')}: ${item && typeof item === 'object' ? '[object]' : String(item)}`);
      return parts.length ? parts.join(' · ') : 'not recorded';
    }
    if (value === undefined || value === null || value === '') return 'not recorded';
    return String(value);
  }

  function _activityDetailsList(details) {
    const list = _node('dl', 'options-team-activity-detail-list');
    list.classList.add('nice-scroll');
    const entries = details && typeof details === 'object' ? Object.entries(details) : [];
    if (!entries.length) {
      list.append(_node('dt', '', 'details'), _node('dd', '', 'not recorded'));
      return list;
    }
    entries.forEach(([key, value]) => {
      list.append(
        _node('dt', '', String(key || '').replaceAll('_', ' ')),
        _node('dd', '', _activityDetailValue(value)),
      );
    });
    return list;
  }

  function _bindActivityDisclosure(toggle, panel) {
    const bindDisclosure = (typeof importedBindDisclosure !== 'undefined' && importedBindDisclosure)
      || null;
    const disclosure = typeof bindDisclosure === 'function'
      ? bindDisclosure(toggle, {
        panel,
        openClass: null,
        hiddenClass: 'u-hidden',
        preventFocusTheft: true,
        clearPressStyle: true,
      })
      : null;
    if (disclosure) return;
    toggle.addEventListener('click', () => {
      const expanded = toggle.getAttribute('aria-expanded') === 'true';
      toggle.setAttribute('aria-expanded', expanded ? 'false' : 'true');
      panel.classList.toggle('u-hidden', expanded);
    });
  }

  function _renderActivityDisclosure(details, panelId) {
    const wrap = _node('div', 'options-team-activity-details');
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'options-team-activity-details-toggle';
    toggle.setAttribute('aria-expanded', 'false');
    if (panelId) toggle.setAttribute('aria-controls', panelId);
    const chev = _node('span', 'disclosure-chev', '▸');
    chev.setAttribute('aria-hidden', 'true');
    toggle.append(chev, _node('span', '', 'details'));
    const list = _activityDetailsList(details);
    list.classList.add('u-hidden');
    if (panelId) list.id = panelId;
    _bindActivityDisclosure(toggle, list);
    wrap.append(toggle, list);
    return wrap;
  }

  function _renderActivityFilters(teamId, st) {
    const form = _node('div', 'options-team-activity-filters');
    form.dataset.teamActivityFilters = teamId;
    const eventType = _input('event_type', 'team.role_change', st.filters.event_type);
    eventType.dataset.teamActivityFilter = 'event_type';
    const actor = _input('actor', 'name or member id', st.filters.actor);
    actor.dataset.teamActivityFilter = 'actor';
    const targetType = _select('target_type', TEAM_ACTIVITY_TARGET_TYPES, st.filters.target_type);
    targetType.dataset.teamActivityFilter = 'target_type';
    const targetId = _input('target_id', 'target id', st.filters.target_id);
    targetId.dataset.teamActivityFilter = 'target_id';
    const from = _input('date_from', '', st.filters.date_from, { type: 'date' });
    from.dataset.teamActivityFilter = 'date_from';
    const to = _input('date_to', '', st.filters.date_to, { type: 'date' });
    to.dataset.teamActivityFilter = 'date_to';
    form.append(
      _field('Event type', eventType),
      _field('Actor', actor),
      _field('Target type', targetType),
      _field('Target id', targetId),
      _field('From', from),
      _field('To', to),
    );
    const actions = _node('div', 'options-session-token-actions options-team-field-full');
    const apply = _button('Apply', 'activity-apply');
    apply.dataset.teamId = teamId;
    const clear = _button('Clear', 'activity-clear', { role: 'ghost' });
    clear.dataset.teamId = teamId;
    actions.append(apply, clear);
    form.appendChild(actions);
    return form;
  }

  function _renderActivityRows(teamId, st) {
    if (st.loading && !st.loaded) return _node('div', 'options-team-empty', 'Loading team activity...');
    if (st.error) {
      const panel = _node('div', 'options-team-empty-state');
      panel.appendChild(_node('div', 'options-team-empty', st.error));
      const retry = _button('Retry', 'activity-retry');
      retry.dataset.teamId = teamId;
      panel.appendChild(retry);
      return panel;
    }
    if (!st.events.length) {
      const panel = _node('div', 'options-team-empty-state');
      panel.appendChild(_node(
        'div',
        'options-team-empty',
        _hasActivityFilters(st) ? 'No team activity matches these filters.' : 'No team activity yet.'
      ));
      if (!_hasActivityFilters(st) && st.retentionDays > 0) {
        panel.appendChild(_node(
          'div',
          'options-team-meta',
          `Audit rows older than ${st.retentionDays} days may no longer be available.`
        ));
      }
      return panel;
    }
    const wrap = _node('div', 'options-team-activity-table-wrap nice-scroll');
    const table = document.createElement('table');
    table.className = 'options-team-activity-table';
    const thead = document.createElement('thead');
    const head = document.createElement('tr');
    ['Time', 'Actor', 'Action', 'Target', 'Summary', 'Details'].forEach((label) => {
      head.appendChild(_node('th', '', label));
    });
    thead.appendChild(head);
    const tbody = document.createElement('tbody');
    st.events.forEach((event, index) => {
      const row = document.createElement('tr');
      [
        _formatDate(event.created) || String(event.created || ''),
        _activityActorLabel(event),
        _titleize(event.event_type),
        _activityTargetLabel(event),
        _activitySummary(event.details),
      ].forEach((text) => {
        row.appendChild(_node('td', '', text));
      });
      const detailsCell = document.createElement('td');
      const safeId = String(event?.id || index).replace(/[^a-zA-Z0-9_-]/g, '-');
      const details = _renderActivityDisclosure(event.details, `options-team-activity-details-${safeId}`);
      detailsCell.appendChild(details);
      row.appendChild(detailsCell);
      tbody.appendChild(row);
    });
    table.append(thead, tbody);
    wrap.appendChild(table);
    return wrap;
  }

  function _renderActivityPager(teamId, st) {
    const pager = _node('div', 'options-team-activity-pager');
    const start = st.events.length ? st.offset + 1 : 0;
    const end = st.offset + st.events.length;
    pager.appendChild(_node('span', 'options-team-meta', st.events.length ? `${start}-${end} shown` : '0 shown'));
    const prev = _button('Previous', 'activity-prev', { role: 'ghost' });
    prev.dataset.teamId = teamId;
    prev.disabled = st.loading || st.offset <= 0;
    const next = _button('Next', 'activity-next', { role: 'ghost' });
    next.dataset.teamId = teamId;
    next.disabled = st.loading || !st.hasMore;
    pager.append(prev, next);
    return pager;
  }

  async function _loadTeamActivity(teamId, options = {}) {
    const normalized = String(teamId || '').trim();
    if (!normalized) return false;
    const st = _activityState(normalized);
    st.offset = Math.max(0, Number(options.offset ?? st.offset) || 0);
    st.loading = true;
    st.error = '';
    if (options.render !== false) _renderDetail();
    try {
      const response = await _jsonRequest(`/session/teams/${encodeURIComponent(normalized)}/activity?${_activityParams(st).toString()}`);
      st.events = Array.isArray(response.events) ? response.events : [];
      st.hasMore = !!response.has_more;
      st.limit = Math.max(1, Number(response.limit || st.limit) || st.limit);
      st.offset = Math.max(0, Number(response.offset || 0) || 0);
      st.retentionDays = Math.max(0, Number(response.retention_days || 0) || 0);
      st.loaded = true;
      return true;
    } catch (error) {
      st.error = error.message || 'Could not load team activity.';
      _logTeamUiActionFailure('load_team_activity', error, { team_id: normalized });
      return false;
    } finally {
      st.loading = false;
      if (options.render !== false) _renderDetail();
    }
  }

  async function _loadTeamRecentActivity(teamId, options = {}) {
    const normalized = String(teamId || '').trim();
    if (!normalized) return false;
    const st = _recentActivityState(normalized);
    st.loading = true;
    st.error = '';
    if (options.render !== false) _renderDetail();
    const params = new URLSearchParams({
      target_type: 'team',
      target_id: normalized,
      limit: '5',
      offset: '0',
    });
    try {
      const response = await _jsonRequest(`/session/teams/${encodeURIComponent(normalized)}/activity?${params.toString()}`);
      st.events = Array.isArray(response.events) ? response.events : [];
      st.hasMore = !!response.has_more;
      st.loaded = true;
      return true;
    } catch (error) {
      st.error = error.message || 'Could not load recent team activity.';
      _logTeamUiActionFailure('load_team_recent_activity', error, { team_id: normalized });
      return false;
    } finally {
      st.loading = false;
      if (options.render !== false) _renderDetail();
    }
  }

  function _renderActivity(section, teamId) {
    const st = _activityState(teamId);
    section.appendChild(_renderActivityFilters(teamId, st));
    section.appendChild(_renderActivityRows(teamId, st));
    section.appendChild(_renderActivityPager(teamId, st));
    if (!st.loaded && !st.loading && !st.error) {
      _loadTeamActivity(teamId).catch(error => _logTeamUiActionFailure('load_team_activity', error, { team_id: teamId }));
    }
  }

  function _renderRecentActivity(section, teamId) {
    const st = _recentActivityState(teamId);
    const header = _node('div', 'options-team-section-title', 'Recent activity');
    section.appendChild(header);
    if (st.loading && !st.loaded) {
      section.appendChild(_node('div', 'options-team-empty', 'Loading recent activity...'));
    } else if (st.error) {
      section.appendChild(_node('div', 'options-team-empty', st.error));
    } else if (!st.events.length) {
      section.appendChild(_node('div', 'options-team-empty', 'No recent team activity yet.'));
    } else {
      const list = _node('div', 'options-team-recent-activity-list');
      st.events.slice(0, 5).forEach((event) => {
        const row = _node('div', 'options-team-recent-activity-row panel-row');
        const main = _node('div', 'options-team-row-main');
        main.append(
          _node('div', 'options-team-name', _titleize(event.event_type)),
          _node('div', 'options-team-meta', _activitySummary(event.details))
        );
        row.append(
          main,
          _node('div', 'options-team-meta', _activityActorLabel(event)),
          _node('div', 'options-team-meta', _formatDate(event.created) || String(event.created || ''))
        );
        list.appendChild(row);
      });
      section.appendChild(list);
    }
    if (st.hasMore || st.events.length) {
      const actions = _node('div', 'options-session-token-actions');
      const viewAll = _button('View activity', 'detail-tab', { role: 'ghost' });
      viewAll.dataset.teamDetailTab = 'activity';
      viewAll.dataset.teamId = teamId;
      actions.appendChild(viewAll);
      section.appendChild(actions);
    }
    if (!st.loaded && !st.loading && !st.error) {
      _loadTeamRecentActivity(teamId).catch(error => _logTeamUiActionFailure('load_team_recent_activity', error, { team_id: teamId }));
    }
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

    if (!_canViewTeamActivity() && _activeDetailTab === 'activity') _activeDetailTab = 'overview';
    if (_canViewTeamActivity()) {
      const tabs = _node('div', 'options-team-detail-tabs tab-strip');
      tabs.setAttribute('role', 'tablist');
      tabs.setAttribute('aria-label', 'Team detail sections');
      [
        ['overview', 'Overview'],
        ['activity', 'Activity'],
      ].forEach(([id, label]) => {
        const active = id === _activeDetailTab;
        const tab = document.createElement('button');
        tab.type = 'button';
        tab.className = 'options-team-detail-tab tab-strip-item';
        tab.textContent = label;
        tab.dataset.teamAction = 'detail-tab';
        tab.dataset.teamDetailTab = id;
        tab.dataset.teamId = team.id || '';
        tab.id = `options-team-detail-tab-${id}`;
        tab.classList.toggle('is-active', active);
        tab.setAttribute('role', 'tab');
        tab.setAttribute('aria-selected', active ? 'true' : 'false');
        tab.setAttribute('aria-controls', `options-team-detail-${id}`);
        tabs.appendChild(tab);
      });
      panel.appendChild(tabs);
    }

    if (_activeDetailTab === 'activity' && _canViewTeamActivity()) {
      const activity = _node('div', 'options-team-section');
      activity.id = 'options-team-detail-activity';
      activity.setAttribute('role', 'tabpanel');
      activity.setAttribute('aria-labelledby', 'options-team-detail-tab-activity');
      _renderActivity(activity, team.id);
      panel.appendChild(activity);
    } else {
      const overview = _node('div', 'options-team-detail-overview');
      if (_canViewTeamActivity()) {
        overview.id = 'options-team-detail-overview';
        overview.setAttribute('role', 'tabpanel');
        overview.setAttribute('aria-labelledby', 'options-team-detail-tab-overview');
      }
      if (_canViewTeamActivity()) {
        const recent = _node('div', 'options-team-section');
        _renderRecentActivity(recent, team.id);
        overview.appendChild(recent);
      }

      const members = _node('div', 'options-team-section');
      _renderMembers(members);
      overview.appendChild(members);

      const invites = _node('div', 'options-team-section');
      _renderInvites(invites);
      overview.appendChild(invites);

      const recovery = _node('div', 'options-team-section');
      _renderRecovery(recovery);
      overview.appendChild(recovery);
      panel.appendChild(overview);
    }

    host.appendChild(panel);
    const enhanceSelects = (typeof importedEnhanceAppSelects !== 'undefined' && importedEnhanceAppSelects)
      || null;
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
    if (_selectedTeamId !== normalized) _activeDetailTab = 'overview';
    _selectedTeamId = normalized;
    _detail = null;
    _renderDetail();
    _setBusy(true);
    try {
      _detail = await _jsonRequest(`/session/teams/${encodeURIComponent(normalized)}`);
      _recentActivityStates.delete(normalized);
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
    const confirmModal = (typeof importedShowConfirm !== 'undefined' && importedShowConfirm)
      || null;
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
      if (_setActiveTeamScope('', { source: 'selector' })) {
        _toast('Personal scope selected');
        _render();
      }
    } else if (action === 'switch-team') {
      if (_setActiveTeamScope(teamId, { source: 'selector' })) {
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
    if (action === 'detail-tab') {
      const nextTab = target.dataset.teamDetailTab || 'overview';
      _activeDetailTab = nextTab === 'activity' && _canViewTeamActivity() ? 'activity' : 'overview';
      _renderDetail();
      return;
    }
    if (action === 'activity-apply' || action === 'activity-clear' || action === 'activity-prev'
        || action === 'activity-next' || action === 'activity-retry') {
      const st = _activityState(teamId);
      if (action === 'activity-apply') {
        _readActivityFilters(target.closest('[data-team-activity-filters]') || _el('options-team-detail'), st);
        await _loadTeamActivity(teamId, { offset: 0 });
      } else if (action === 'activity-clear') {
        _resetActivityFilters(st);
        await _loadTeamActivity(teamId, { offset: 0 });
      } else if (action === 'activity-prev') {
        await _loadTeamActivity(teamId, { offset: Math.max(0, st.offset - st.limit) });
      } else if (action === 'activity-next') {
        await _loadTeamActivity(teamId, { offset: st.offset + st.limit });
      } else {
        await _loadTeamActivity(teamId);
      }
      return;
    }
    if (action === 'switch-team') {
      if (_setActiveTeamScope(teamId, { source: 'selector' })) {
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
    const panel = _el('options-panel-teams');
    if (panel) panel.dataset.teamsPanelBound = '1';
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
    panel?.addEventListener('submit', (event) => {
      if (!event.target?.matches?.('[data-team-form]')) return;
      event.preventDefault();
      const mode = event.target.dataset.teamForm || 'unknown';
      const action = mode === 'create'
        ? 'create_team'
        : (mode === 'recover' ? 'redeem_recovery_code' : 'join_team');
      _submitTopForm(event.target).catch(error => _logTeamUiActionFailure(action, error));
    });
    panel?.addEventListener('click', (event) => {
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
  exportedRefreshOptionsTeams = refreshOptionsTeams;
})(window);

export { exportedRefreshOptionsTeams as refreshOptionsTeams };
