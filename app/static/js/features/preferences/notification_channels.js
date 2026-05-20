// Options modal outbound-notification channel management.
(function (global) {
  const CHANNEL_KINDS = [
    { value: 'webhook', label: 'Webhook' },
    { value: 'slack', label: 'Slack' },
    { value: 'discord', label: 'Discord' },
    { value: 'telegram', label: 'Telegram' },
    { value: 'pushover', label: 'Pushover' },
    { value: 'email', label: 'Email' },
  ];
  const TRIGGERS = [
    { value: 'run_complete', label: 'Run complete' },
    { value: 'pty_session_ended', label: 'PTY session ended' },
    { value: 'scheduled_run_failed', label: 'Scheduled run failed' },
    { value: 'watcher_changed', label: 'Watcher changed' },
    { value: 'watcher_error', label: 'Watcher error' },
    { value: 'watcher_recovered', label: 'Watcher recovered' },
  ];
  const SECRET_FIELDS = {
    webhook: [{ name: 'url', label: 'Webhook URL' }],
    slack: [{ name: 'url', label: 'Slack webhook URL' }],
    discord: [{ name: 'url', label: 'Discord webhook URL' }],
    telegram: [{ name: 'bot_token', label: 'Bot token' }],
    pushover: [
      { name: 'app_token', label: 'App token' },
      { name: 'user_key', label: 'User key' },
    ],
    email: [],
  };
  const CONFIG_FIELDS = {
    webhook: [{ name: 'timeout_seconds', label: 'Timeout seconds', optional: true }],
    slack: [{ name: 'timeout_seconds', label: 'Timeout seconds', optional: true }],
    discord: [{ name: 'timeout_seconds', label: 'Timeout seconds', optional: true }],
    telegram: [
      { name: 'chat_id', label: 'Chat ID' },
      { name: 'timeout_seconds', label: 'Timeout seconds', optional: true },
    ],
    pushover: [
      { name: 'priority', label: 'Priority', optional: true },
      { name: 'sound', label: 'Sound', optional: true },
      { name: 'device', label: 'Device', optional: true },
      { name: 'timeout_seconds', label: 'Timeout seconds', optional: true },
    ],
    email: [
      { name: 'recipients', label: 'Recipients', help: 'Comma-separated email addresses.' },
      { name: 'reply_to', label: 'Reply-To', optional: true },
      { name: 'timeout_seconds', label: 'Timeout seconds', optional: true },
    ],
  };

  let _channelsCache = null;
  let _channelsLoading = false;
  let _bound = false;

  function _el(id) {
    return document.getElementById(id);
  }

  function _apiFetch() {
    return typeof global.apiFetch === 'function' ? global.apiFetch.bind(global) : global.fetch.bind(global);
  }

  function _msg(text, { error = false } = {}) {
    const node = _el('options-notification-msg');
    if (!node) return;
    node.textContent = text || '';
    node.classList.toggle('is-error', !!error);
    node.style.display = text ? '' : 'none';
  }

  function _toast(text, tone = 'success') {
    _msg('');
    if (typeof global.showToast === 'function') {
      global.showToast(text, tone);
      return;
    }
    _msg(text, { error: tone === 'error' });
  }

  function _setBusy(busy) {
    _channelsLoading = !!busy;
    ['options-notification-refresh-btn', 'options-notification-new-btn'].forEach((id) => {
      const button = _el(id);
      if (button) button.disabled = _channelsLoading;
    });
  }

  function _kindLabel(kind) {
    return CHANNEL_KINDS.find(item => item.value === kind)?.label || String(kind || 'Channel');
  }

  function _secretConfigured(channel, name) {
    return (channel.secret_fields || []).some(field => field.name === name && field.configured);
  }

  function _field(label, input) {
    const wrapper = document.createElement('label');
    wrapper.className = 'options-secret-field';
    const text = document.createElement('span');
    text.className = 'options-secret-field-label';
    text.textContent = label;
    wrapper.append(text, input);
    return wrapper;
  }

  function _input(value = '', attrs = {}) {
    const input = document.createElement('input');
    input.className = 'form-control form-control-compact options-token-input';
    input.type = attrs.type || 'text';
    input.value = value || '';
    Object.entries(attrs).forEach(([key, attrValue]) => {
      if (key !== 'type') input.setAttribute(key, attrValue);
    });
    return input;
  }

  function _select(value, options, attrs = {}) {
    const select = document.createElement('select');
    select.className = 'form-select';
    Object.entries(attrs).forEach(([key, attrValue]) => select.setAttribute(key, attrValue));
    options.forEach((option) => {
      const node = document.createElement('option');
      node.value = option.value;
      node.textContent = option.label;
      select.appendChild(node);
    });
    select.value = value || options[0]?.value || '';
    return select;
  }

  function _triggerChecks(selected) {
    const selectedSet = new Set(Array.isArray(selected) && selected.length ? selected : ['run_complete']);
    const wrapper = document.createElement('div');
    wrapper.className = 'options-secret-field';
    const label = document.createElement('div');
    label.className = 'options-secret-field-label';
    label.textContent = 'Triggers';
    const list = document.createElement('div');
    list.className = 'form-fieldset';
    TRIGGERS.forEach((trigger) => {
      const row = document.createElement('label');
      row.className = 'form-check';
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.value = trigger.value;
      input.checked = selectedSet.has(trigger.value);
      const text = document.createElement('span');
      text.textContent = trigger.label;
      row.append(input, text);
      list.appendChild(row);
    });
    wrapper.append(label, list);
    return { wrapper, list };
  }

  function _channelConfigSummary(channel) {
    const config = channel.config || {};
    if (channel.kind === 'email' && Array.isArray(config.recipients) && config.recipients.length) {
      return `${config.recipients.length} recipients`;
    }
    if (channel.kind === 'telegram' && config.chat_id) return `chat ${config.chat_id}`;
    return '';
  }

  function _renderChannels(channels) {
    const list = _el('options-notification-list');
    if (!list) return;
    list.innerHTML = '';
    if (!Array.isArray(channels) || channels.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'options-secret-empty options-secret-empty-state';
      const title = document.createElement('div');
      title.textContent = 'No notification channels yet.';
      const hint = document.createElement('div');
      hint.className = 'options-secret-meta';
      hint.textContent = 'Add a channel to get pinged when long runs finish.';
      empty.append(title, hint);
      list.appendChild(empty);
      return;
    }
    channels.forEach((channel) => {
      const row = document.createElement('div');
      row.className = 'options-secret-row';
      const body = document.createElement('div');
      body.className = 'options-secret-row-body';
      const name = document.createElement('div');
      name.className = 'options-secret-name';
      name.textContent = channel.label || _kindLabel(channel.kind);
      const chips = document.createElement('div');
      chips.className = 'options-secret-chips';
      [
        { text: _kindLabel(channel.kind), className: 'badge badge-tone-muted options-secret-chip' },
        {
          text: channel.muted ? 'muted' : 'active',
          className: `badge ${channel.muted ? 'badge-tone-muted is-muted' : 'badge-tone-green'} options-secret-chip`,
        },
      ].forEach((chipConfig) => {
        const chip = document.createElement('span');
        chip.className = chipConfig.className;
        chip.textContent = chipConfig.text;
        chips.appendChild(chip);
      });
      const meta = document.createElement('div');
      meta.className = 'options-secret-meta';
      const summary = _channelConfigSummary(channel);
      const triggers = (channel.triggers || []).map(trigger => trigger.replaceAll('_', ' ')).join(', ') || 'run complete';
      meta.textContent = [triggers, summary].filter(Boolean).join(' · ');
      body.append(name, chips, meta);

      const actions = document.createElement('div');
      actions.className = 'options-secret-actions';
      const mute = document.createElement('button');
      mute.type = 'button';
      mute.className = 'btn btn-secondary btn-compact';
      mute.textContent = channel.muted ? 'Unmute' : 'Mute';
      mute.addEventListener('click', () => toggleNotificationChannelMuted(channel));
      const test = document.createElement('button');
      test.type = 'button';
      test.className = 'btn btn-secondary btn-compact';
      test.textContent = 'Test';
      test.addEventListener('click', () => testNotificationChannel(channel));
      const edit = document.createElement('button');
      edit.type = 'button';
      edit.className = 'btn btn-secondary btn-compact';
      edit.textContent = 'Edit';
      edit.addEventListener('click', () => openNotificationChannelEditor(channel));
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'btn btn-destructive btn-compact';
      remove.textContent = 'Delete';
      remove.addEventListener('click', () => deleteNotificationChannel(channel));
      actions.append(mute, test, edit, remove);
      row.append(body, actions);
      list.appendChild(row);
    });
  }

  async function refreshNotificationChannels({ force = false } = {}) {
    if (_channelsLoading && !force) return _channelsCache || [];
    if (_channelsCache && !force) {
      _renderChannels(_channelsCache);
      _msg('');
      return _channelsCache;
    }
    _setBusy(true);
    try {
      const resp = await _apiFetch()('/session/notification-channels');
      const data = await resp.json().catch(() => ({}));
      if (resp && resp.ok === false) throw new Error(data.message || data.error || `HTTP ${resp.status}`);
      _channelsCache = Array.isArray(data.channels) ? data.channels : [];
      _renderChannels(_channelsCache);
      _msg('');
      return _channelsCache;
    } catch (error) {
      if (_channelsCache) {
        _renderChannels(_channelsCache);
      } else {
        _renderChannels([]);
      }
      const message = error.message === 'session_token_required'
        ? 'Generate or set a session token before adding notification channels.'
        : `Could not load notification channels: ${error.message || 'network error'}`;
      _msg(message, { error: true });
      return [];
    } finally {
      _setBusy(false);
    }
  }

  function _buildEditor(channel) {
    const content = document.createElement('div');
    content.className = 'form-fieldset';
    const kindSelect = _select(channel?.kind || 'webhook', CHANNEL_KINDS, { 'aria-label': 'Notification channel type' });
    kindSelect.disabled = !!channel;
    const labelInput = _input(channel?.label || '', {
      maxlength: '80',
      autocomplete: 'off',
      placeholder: 'Label',
    });
    const dynamicFields = document.createElement('div');
    const error = document.createElement('div');
    error.className = 'form-error';
    error.style.display = 'none';

    const triggerControls = _triggerChecks(channel?.triggers || ['run_complete']);
    content.append(
      _field('Type', kindSelect),
      _field('Label', labelInput),
      dynamicFields,
      triggerControls.wrapper,
      error,
    );

    const renderDynamicFields = () => {
      dynamicFields.innerHTML = '';
      const kind = kindSelect.value;
      SECRET_FIELDS[kind].forEach((field) => {
        const input = _input('', {
          type: 'password',
          autocomplete: 'off',
          placeholder: channel && _secretConfigured(channel, field.name) ? 'Leave blank to keep existing' : field.label,
        });
        input.dataset.secretField = field.name;
        dynamicFields.appendChild(_field(field.label, input));
      });
      CONFIG_FIELDS[kind].forEach((field) => {
        const value = field.name === 'recipients' && Array.isArray(channel?.config?.recipients)
          ? channel.config.recipients.join(', ')
          : (channel?.config?.[field.name] || '');
        const input = _input(value, {
          autocomplete: 'off',
          placeholder: field.optional ? 'Optional' : field.label,
        });
        input.dataset.configField = field.name;
        dynamicFields.appendChild(_field(field.label, input));
        if (field.help) {
          const help = document.createElement('div');
          help.className = 'options-secret-meta';
          help.textContent = field.help;
          dynamicFields.appendChild(help);
        }
      });
    };
    kindSelect.addEventListener('change', renderDynamicFields);
    renderDynamicFields();

    return { content, kindSelect, labelInput, dynamicFields, triggerControls, error };
  }

  function _readEditor(editor, channel) {
    const kind = editor.kindSelect.value;
    const secretValues = {};
    editor.dynamicFields.querySelectorAll('[data-secret-field]').forEach((input) => {
      if (input.value) secretValues[input.dataset.secretField] = input.value;
    });
    const config = {};
    editor.dynamicFields.querySelectorAll('[data-config-field]').forEach((input) => {
      const key = input.dataset.configField;
      const value = String(input.value || '').trim();
      if (!value) return;
      config[key] = key === 'recipients'
        ? value.split(',').map(item => item.trim()).filter(Boolean)
        : value;
    });
    const triggers = Array.from(editor.triggerControls.list.querySelectorAll('input[type="checkbox"]:checked'))
      .map(input => input.value);
    const missingSecret = SECRET_FIELDS[kind]
      .find(field => !secretValues[field.name] && !(channel && channel.kind === kind && _secretConfigured(channel, field.name)));
    if (missingSecret) return { error: `${missingSecret.label} is required.` };
    return {
      kind,
      label: editor.labelInput.value,
      config,
      triggers,
      secret_values: secretValues,
      muted: !!channel?.muted,
    };
  }

  async function _saveEditor(channel, editor) {
    editor.error.style.display = 'none';
    const payload = _readEditor(editor, channel);
    if (payload.error) {
      editor.error.textContent = payload.error;
      editor.error.style.display = '';
      return false;
    }
    try {
      const url = channel
        ? `/session/notification-channels/${encodeURIComponent(channel.id)}`
        : '/session/notification-channels';
      const resp = await _apiFetch()(url, {
        method: channel ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await resp.json().catch(() => ({}));
      if (resp && resp.ok === false) throw new Error(data.message || data.error || `HTTP ${resp.status}`);
      _channelsCache = null;
      await refreshNotificationChannels({ force: true });
      _toast(channel ? 'Notification channel updated.' : 'Notification channel added.');
      return true;
    } catch (error) {
      _toast(`Save failed: ${error.message || 'network error'}`, 'error');
      return false;
    }
  }

  async function openNotificationChannelEditor(channel = null) {
    if (typeof global.showConfirm !== 'function') return null;
    const editor = _buildEditor(channel);
    return global.showConfirm({
      body: {
        text: channel ? 'Update notification channel.' : 'Add a notification channel.',
        note: 'Secret values are sent once, stored in the vault, and never displayed again.',
      },
      content: editor.content,
      defaultFocus: editor.labelInput,
      actions: [
        { id: 'cancel', label: 'Cancel', role: 'cancel' },
        {
          id: 'save',
          label: channel ? 'Save' : 'Add',
          role: 'primary',
          onActivate: () => _saveEditor(channel, editor),
        },
      ],
    });
  }

  async function toggleNotificationChannelMuted(channel) {
    const payload = {
      kind: channel.kind,
      label: channel.label,
      config: channel.config || {},
      triggers: channel.triggers || ['run_complete'],
      muted: !channel.muted,
    };
    _setBusy(true);
    try {
      const resp = await _apiFetch()(`/session/notification-channels/${encodeURIComponent(channel.id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await resp.json().catch(() => ({}));
      if (resp && resp.ok === false) throw new Error(data.message || data.error || `HTTP ${resp.status}`);
      _channelsCache = null;
      await refreshNotificationChannels({ force: true });
      _toast(payload.muted ? 'Notification channel muted.' : 'Notification channel unmuted.');
    } catch (error) {
      _toast(`Update failed: ${error.message || 'network error'}`, 'error');
    } finally {
      _setBusy(false);
    }
  }

  async function testNotificationChannel(channel) {
    _setBusy(true);
    try {
      const resp = await _apiFetch()(`/session/notification-channels/${encodeURIComponent(channel.id)}/test`, {
        method: 'POST',
      });
      const data = await resp.json().catch(() => ({}));
      if (resp && resp.ok === false) throw new Error(data.message || data.error || `HTTP ${resp.status}`);
      const event = Array.isArray(data.events) ? data.events[0] : null;
      if (event?.status === 'sent') {
        _toast('Test notification delivered.');
      } else if (event?.status === 'retry_wait' || event?.status === 'dead') {
        const detail = event.last_error ? `: ${event.last_error}` : '.';
        _toast(`Test notification failed${detail}`, 'error');
      } else {
        _toast(
          data.queued ? 'Test notification queued.' : 'No test notification was queued for this channel.',
          data.queued ? 'success' : 'error',
        );
      }
    } catch (error) {
      _toast(`Test failed: ${error.message || 'network error'}`, 'error');
    } finally {
      _setBusy(false);
    }
  }

  async function deleteNotificationChannel(channel) {
    if (typeof global.showConfirm !== 'function') return false;
    const choice = await global.showConfirm({
      body: {
        text: `Delete ${channel.label || _kindLabel(channel.kind)}?`,
        note: 'The channel will stop receiving outbound notifications.',
      },
      tone: 'danger',
      actions: [
        { id: 'cancel', label: 'Cancel', role: 'cancel' },
        { id: 'delete', label: 'Delete', role: 'destructive' },
      ],
    });
    if (choice !== 'delete') return false;
    _setBusy(true);
    try {
      const resp = await _apiFetch()(`/session/notification-channels/${encodeURIComponent(channel.id)}`, {
        method: 'DELETE',
      });
      const data = await resp.json().catch(() => ({}));
      if (resp && resp.ok === false) throw new Error(data.message || data.error || `HTTP ${resp.status}`);
      _channelsCache = null;
      await refreshNotificationChannels({ force: true });
      _toast('Notification channel deleted.');
      return true;
    } catch (error) {
      _toast(`Delete failed: ${error.message || 'network error'}`, 'error');
      return false;
    } finally {
      _setBusy(false);
    }
  }

  function bindNotificationChannelsPanel() {
    if (_bound) return;
    _bound = true;
    _el('options-notification-refresh-btn')?.addEventListener('click', () => refreshNotificationChannels({ force: true }));
    _el('options-notification-new-btn')?.addEventListener('click', () => openNotificationChannelEditor());
    if (!document.querySelector('[data-options-panel="notifications"]')?.hidden) {
      refreshNotificationChannels();
    }
  }

  bindNotificationChannelsPanel();

  global.refreshNotificationChannels = refreshNotificationChannels;
  global.openNotificationChannelEditor = openNotificationChannelEditor;
})(typeof window !== 'undefined' ? window : globalThis);
