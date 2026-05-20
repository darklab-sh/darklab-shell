// Browser schedules modal and handoff actions.

const SCHEDULES_DEFAULT_CRON = '0 * * * *';
const SCHEDULES_FIRES_LIMIT = 20;
const SCHEDULES_PRESETS = {
  hourly: '0 * * * *',
  daily: '0 0 * * *',
  weekly: '0 0 * * 0',
};
const SCHEDULES_COMMON_TIMEZONES = [
  'UTC',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Phoenix',
  'America/Anchorage',
  'Pacific/Honolulu',
  'Europe/London',
  'Europe/Berlin',
  'Europe/Paris',
  'Asia/Tokyo',
  'Asia/Singapore',
  'Australia/Sydney',
];

let _schedulesState = {
  schedules: [],
  selectedId: '',
  draft: null,
  mode: 'view',
  fires: [],
  firesMeta: { limit: SCHEDULES_FIRES_LIMIT, offset: 0, total: 0, has_more: false },
  loading: false,
  loadingFires: false,
  saving: false,
  preview: { loading: false, error: '', next_fires: [], cron_expr: SCHEDULES_DEFAULT_CRON, timezone: 'UTC' },
  previewTimer: null,
};

function _scheduleEls() {
  return {
    overlay: document.getElementById('schedules-overlay'),
    list: document.getElementById('schedules-list'),
    detail: document.getElementById('schedules-detail'),
    count: document.getElementById('schedules-count'),
    newBtn: document.getElementById('schedules-new-btn'),
    refreshBtn: document.getElementById('schedules-refresh-btn'),
  };
}

function _scheduleTitle(schedule) {
  return String(schedule?.label || schedule?.command_text || schedule?.id || 'Schedule').trim();
}

function _schedulePresetFor(schedule) {
  const preset = String(schedule?.cadence_preset || '').trim().toLowerCase();
  if (preset && SCHEDULES_PRESETS[preset]) return preset;
  const cron = String(schedule?.cron_expr || '').trim();
  const matched = Object.entries(SCHEDULES_PRESETS).find(([, value]) => value === cron);
  return matched ? matched[0] : 'custom';
}

function _scheduleDraftFromSchedule(schedule = null, command = '') {
  const preset = schedule ? _schedulePresetFor(schedule) : 'hourly';
  return {
    id: schedule?.id || '',
    label: String(schedule?.label || '').trim(),
    command_text: String(schedule?.command_text || command || '').trim(),
    cadence_preset: preset,
    cron_expr: String(schedule?.cron_expr || SCHEDULES_PRESETS[preset] || SCHEDULES_DEFAULT_CRON).trim(),
    timezone: String(schedule?.timezone || 'UTC').trim(),
    enabled: schedule ? schedule.enabled !== false : true,
  };
}

function _selectedSchedule() {
  return _schedulesState.schedules.find(item => String(item.id || '') === String(_schedulesState.selectedId || '')) || null;
}

async function _scheduleJson(url, options = {}) {
  const resp = await apiFetch(url, options);
  let data = {};
  try {
    data = await resp.json();
  } catch (_) {
    data = {};
  }
  if (!resp.ok) {
    const message = data?.message || data?.error || `HTTP ${resp.status}`;
    throw new Error(message);
  }
  return data;
}

function _scheduleToast(message, tone = 'success') {
  if (typeof showToast === 'function') showToast(message, tone);
}

function _scheduleDateLabel(value) {
  const raw = String(value || '').trim();
  if (!raw) return 'never';
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  return date.toLocaleString();
}

function _schedulePreviewDateLabel(value, timezone) {
  const raw = String(value || '').trim();
  if (!raw) return 'never';
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  try {
    return date.toLocaleString(undefined, {
      timeZone: timezone || 'UTC',
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      timeZoneName: 'short',
    });
  } catch (_) {
    return _scheduleDateLabel(value);
  }
}

function _scheduleBrowserTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || '';
  } catch (_) {
    return '';
  }
}

function _scheduleTimezoneOptions(selected) {
  const preferred = new Set(['UTC']);
  const browserTimezone = _scheduleBrowserTimezone();
  if (browserTimezone) preferred.add(browserTimezone);
  SCHEDULES_COMMON_TIMEZONES.forEach(zone => preferred.add(zone));
  if (selected) preferred.add(selected);
  let supported = [];
  try {
    supported = typeof Intl.supportedValuesOf === 'function' ? Intl.supportedValuesOf('timeZone') : [];
  } catch (_) {
    supported = [];
  }
  supported.forEach(zone => preferred.add(zone));
  return Array.from(preferred);
}

function _scheduleStatusLabel(schedule) {
  if (!schedule) return '';
  const reason = String(schedule.paused_reason || '').trim();
  if (schedule.enabled === false) {
    return /revok/i.test(reason) ? 'token revoked' : 'paused';
  }
  if (schedule.last_error) return 'needs attention';
  return 'active';
}

function _scheduleStatusTone(schedule) {
  const label = _scheduleStatusLabel(schedule);
  if (label === 'active') return 'badge-tone-green';
  if (label === 'token revoked' || label === 'needs attention') return 'badge-tone-red';
  return 'badge-tone-muted';
}

function _setSchedulesOpen(open) {
  const { overlay } = _scheduleEls();
  if (!overlay) return;
  overlay.classList.toggle('u-hidden', !open);
  overlay.classList.toggle('open', !!open);
  overlay.setAttribute('aria-hidden', open ? 'false' : 'true');
  window.syncModalOverlayState?.();
}

function isSchedulesOverlayOpen() {
  const { overlay } = _scheduleEls();
  return !!(overlay && overlay.classList.contains('open'));
}

function closeSchedulesModal({ refocus = true } = {}) {
  _setSchedulesOpen(false);
  if (refocus && typeof refocusComposerAfterAction === 'function') {
    refocusComposerAfterAction({ preventScroll: true, defer: true });
  }
}

function _renderSchedulesList() {
  const { list, count } = _scheduleEls();
  if (!list) return;
  list.replaceChildren();
  if (count) count.textContent = String(_schedulesState.schedules.length);
  if (_schedulesState.loading) {
    const loading = document.createElement('div');
    loading.className = 'schedules-empty';
    loading.textContent = 'Loading schedules...';
    list.appendChild(loading);
    return;
  }
  if (!_schedulesState.schedules.length) {
    const empty = document.createElement('div');
    empty.className = 'schedules-empty';
    empty.textContent = 'No schedules saved.';
    list.appendChild(empty);
    return;
  }
  _schedulesState.schedules.forEach((schedule) => {
    const row = document.createElement('button');
    row.type = 'button';
    row.className = 'schedules-list-row';
    row.dataset.scheduleId = schedule.id || '';
    if (String(schedule.id || '') === String(_schedulesState.selectedId || '')) row.classList.add('active');
    const title = document.createElement('span');
    title.className = 'schedules-list-title';
    title.textContent = _scheduleTitle(schedule);
    const meta = document.createElement('span');
    meta.className = 'schedules-list-meta';
    const cadence = schedule.cadence_preset || schedule.cron_expr || 'custom';
    meta.textContent = `${cadence} - ${_scheduleDateLabel(schedule.next_run_at)}`;
    const status = document.createElement('span');
    status.className = `badge ${_scheduleStatusTone(schedule)} schedules-list-status`;
    status.textContent = _scheduleStatusLabel(schedule);
    row.append(title, meta, status);
    list.appendChild(row);
  });
}

function _schedulePreviewNode() {
  const wrap = document.createElement('div');
  wrap.className = 'schedules-preview';
  const title = document.createElement('div');
  title.className = 'schedules-section-kicker';
  const timezone = _schedulesState.preview.timezone || _schedulesState.draft?.timezone || 'UTC';
  title.textContent = `Next runs (${timezone})`;
  wrap.appendChild(title);
  if (_schedulesState.preview.loading) {
    const loading = document.createElement('div');
    loading.className = 'schedules-muted';
    loading.textContent = 'Checking...';
    wrap.appendChild(loading);
  } else if (_schedulesState.preview.error) {
    const err = document.createElement('div');
    err.className = 'schedules-error';
    err.textContent = _schedulesState.preview.error;
    wrap.appendChild(err);
  } else {
    const list = document.createElement('div');
    list.className = 'schedules-preview-list';
    (_schedulesState.preview.next_fires || []).forEach((value) => {
      const item = document.createElement('span');
      item.textContent = _schedulePreviewDateLabel(value, timezone);
      list.appendChild(item);
    });
    if (!list.childElementCount) {
      const empty = document.createElement('span');
      empty.className = 'schedules-muted';
      empty.textContent = 'No preview available.';
      list.appendChild(empty);
    }
    wrap.appendChild(list);
  }
  return wrap;
}

function _renderSchedulePreview(parent) {
  parent.appendChild(_schedulePreviewNode());
}

function _updateSchedulePreviewView() {
  const current = document.querySelector('.schedules-preview');
  if (current) current.replaceWith(_schedulePreviewNode());
}

function _scheduleFormField(label, control) {
  const field = document.createElement('label');
  field.className = 'schedules-field';
  const text = document.createElement('span');
  text.className = 'schedules-field-label';
  text.textContent = label;
  field.append(text, control);
  return field;
}

function _scheduleInput(value, attrs = {}) {
  const input = document.createElement('input');
  input.className = 'options-token-input schedules-input';
  input.value = value || '';
  Object.entries(attrs).forEach(([key, attrValue]) => {
    if (attrValue !== null && attrValue !== undefined) input.setAttribute(key, attrValue);
  });
  return input;
}

function _scheduleTimezoneSelect(value) {
  const selectedValue = value || 'UTC';
  const select = document.createElement('select');
  select.id = 'schedules-timezone-input';
  select.className = 'form-select schedules-select';
  _scheduleTimezoneOptions(selectedValue).forEach((timezone) => {
    const option = document.createElement('option');
    option.value = timezone;
    option.textContent = timezone;
    if (timezone === selectedValue) option.selected = true;
    select.appendChild(option);
  });
  if (select.value !== selectedValue) select.value = 'UTC';
  return select;
}

function _setScheduleCadencePreset(value) {
  document.querySelectorAll('.schedules-cadence-btn').forEach((btn) => {
    const active = btn.dataset.schedulePreset === value;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-pressed', active ? 'true' : 'false');
  });
}

function _renderScheduleForm(parent, schedule) {
  const draft = _schedulesState.draft || _scheduleDraftFromSchedule(schedule);
  const form = document.createElement('form');
  form.className = 'schedules-form';
  form.id = 'schedules-form';

  const labelInput = _scheduleInput(draft.label, {
    id: 'schedules-label-input',
    autocomplete: 'off',
    maxlength: '120',
  });
  const commandInput = document.createElement('textarea');
  commandInput.id = 'schedules-command-input';
  commandInput.className = 'options-token-input schedules-command-input';
  commandInput.value = draft.command_text;
  commandInput.rows = 3;
  commandInput.spellcheck = false;
  commandInput.setAttribute('required', 'required');
  const timezoneInput = _scheduleTimezoneSelect(draft.timezone || 'UTC');
  const cronInput = _scheduleInput(draft.cron_expr || SCHEDULES_DEFAULT_CRON, {
    id: 'schedules-cron-input',
    autocomplete: 'off',
    required: 'required',
  });

  form.append(
    _scheduleFormField('Label', labelInput),
    _scheduleFormField('Command', commandInput),
  );

  const cadence = document.createElement('div');
  cadence.className = 'schedules-field schedules-cadence-field';
  const cadenceLabel = document.createElement('span');
  cadenceLabel.className = 'schedules-field-label';
  cadenceLabel.textContent = 'Cadence';
  const cadenceControls = document.createElement('div');
  cadenceControls.className = 'schedules-cadence-controls';
  [
    ['hourly', 'Every hour'],
    ['daily', 'Daily'],
    ['weekly', 'Weekly'],
    ['custom', 'Custom cron'],
  ].forEach(([preset, label]) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'toggle-btn schedules-cadence-btn';
    btn.dataset.schedulePreset = preset;
    btn.setAttribute('aria-pressed', draft.cadence_preset === preset ? 'true' : 'false');
    if (draft.cadence_preset === preset) btn.classList.add('active');
    btn.textContent = label;
    cadenceControls.appendChild(btn);
  });
  cadence.append(cadenceLabel, cadenceControls);
  form.appendChild(cadence);
  form.append(
    _scheduleFormField('Cron', cronInput),
    _scheduleFormField('Timezone', timezoneInput),
  );

  const enabledLabel = document.createElement('label');
  enabledLabel.className = 'schedules-check-row';
  const enabled = document.createElement('input');
  enabled.type = 'checkbox';
  enabled.id = 'schedules-enabled-input';
  enabled.checked = draft.enabled !== false;
  const enabledText = document.createElement('span');
  enabledText.textContent = 'Enabled';
  enabledLabel.append(enabled, enabledText);
  form.appendChild(enabledLabel);

  _renderSchedulePreview(form);

  const actions = document.createElement('div');
  actions.className = 'schedules-detail-actions';
  const saveBtn = document.createElement('button');
  saveBtn.type = 'submit';
  saveBtn.className = 'btn btn-primary btn-compact';
  saveBtn.disabled = _schedulesState.saving;
  saveBtn.textContent = schedule ? 'Save' : 'Create';
  actions.appendChild(saveBtn);
  if (schedule) {
    const toggleBtn = document.createElement('button');
    toggleBtn.type = 'button';
    toggleBtn.className = 'btn btn-secondary btn-compact';
    toggleBtn.dataset.scheduleAction = schedule.enabled === false ? 'resume' : 'pause';
    toggleBtn.textContent = schedule.enabled === false ? 'Resume' : 'Pause';
    const runBtn = document.createElement('button');
    runBtn.type = 'button';
    runBtn.className = 'btn btn-secondary btn-compact';
    runBtn.dataset.scheduleAction = 'run-now';
    runBtn.textContent = 'Run now';
    const deleteBtn = document.createElement('button');
    deleteBtn.type = 'button';
    deleteBtn.className = 'btn btn-ghost btn-compact';
    deleteBtn.dataset.scheduleAction = 'delete';
    deleteBtn.textContent = 'Delete';
    actions.append(toggleBtn, runBtn, deleteBtn);
  }
  form.appendChild(actions);
  parent.appendChild(form);
}

function _renderScheduleFires(parent, schedule) {
  if (!schedule) return;
  const section = document.createElement('div');
  section.className = 'schedules-fires';
  const header = document.createElement('div');
  header.className = 'schedules-section-header';
  const title = document.createElement('h3');
  title.textContent = 'Past fires';
  const refresh = document.createElement('button');
  refresh.type = 'button';
  refresh.className = 'btn btn-ghost btn-compact';
  refresh.dataset.scheduleAction = 'refresh-fires';
  refresh.textContent = 'Refresh';
  header.append(title, refresh);
  section.appendChild(header);
  if (_schedulesState.loadingFires) {
    const loading = document.createElement('div');
    loading.className = 'schedules-empty';
    loading.textContent = 'Loading fires...';
    section.appendChild(loading);
  } else if (!_schedulesState.fires.length) {
    const empty = document.createElement('div');
    empty.className = 'schedules-empty';
    empty.textContent = 'No fires yet.';
    section.appendChild(empty);
  } else {
    const rows = document.createElement('div');
    rows.className = 'schedules-fire-list';
    _schedulesState.fires.forEach((fire) => {
      const row = document.createElement('div');
      row.className = 'schedules-fire-row';
      const main = document.createElement('div');
      main.className = 'schedules-fire-main';
      const status = document.createElement('span');
      status.className = 'schedules-fire-status';
      status.textContent = fire.status || 'fire';
      const date = document.createElement('span');
      date.className = 'schedules-fire-date';
      date.textContent = _scheduleDateLabel(fire.fired_at);
      main.append(status, date);
      const reason = document.createElement('div');
      reason.className = 'schedules-fire-reason';
      reason.textContent = fire.reason || '';
      row.append(main, reason);
      if (fire.run_id) {
        const open = document.createElement('button');
        open.type = 'button';
        open.className = 'btn btn-secondary btn-compact';
        open.dataset.scheduleRunId = fire.run_id;
        open.textContent = 'Open run';
        row.appendChild(open);
      }
      rows.appendChild(row);
    });
    section.appendChild(rows);
  }
  const meta = _schedulesState.firesMeta || {};
  if (Number(meta.total || 0) > Number(meta.limit || SCHEDULES_FIRES_LIMIT)) {
    const pager = document.createElement('div');
    pager.className = 'schedules-pager';
    const prev = document.createElement('button');
    prev.type = 'button';
    prev.className = 'btn btn-secondary btn-compact';
    prev.dataset.scheduleFiresPage = 'prev';
    prev.disabled = Number(meta.offset || 0) <= 0;
    prev.textContent = 'Prev';
    const label = document.createElement('span');
    label.className = 'schedules-muted';
    const start = Number(meta.offset || 0) + 1;
    const end = Math.min(Number(meta.total || 0), Number(meta.offset || 0) + _schedulesState.fires.length);
    label.textContent = `${start}-${end} / ${Number(meta.total || 0).toLocaleString()}`;
    const next = document.createElement('button');
    next.type = 'button';
    next.className = 'btn btn-secondary btn-compact';
    next.dataset.scheduleFiresPage = 'next';
    next.disabled = !meta.has_more;
    next.textContent = 'Next';
    pager.append(prev, label, next);
    section.appendChild(pager);
  }
  parent.appendChild(section);
}

function _renderSchedulesDetail() {
  const { detail } = _scheduleEls();
  if (!detail) return;
  detail.replaceChildren();
  const schedule = _selectedSchedule();
  const isNew = _schedulesState.mode === 'new';
  const root = document.createElement('div');
  root.className = 'schedules-detail-inner';
  if (!schedule && !isNew) {
    const empty = document.createElement('div');
    empty.className = 'schedules-empty schedules-detail-empty';
    empty.textContent = 'Select or create a schedule.';
    root.appendChild(empty);
    detail.appendChild(root);
    return;
  }
  const header = document.createElement('div');
  header.className = 'schedules-detail-header';
  const title = document.createElement('div');
  title.className = 'schedules-detail-title';
  title.textContent = isNew ? 'New schedule' : _scheduleTitle(schedule);
  header.appendChild(title);
  if (schedule) {
    const status = document.createElement('span');
    status.className = `badge ${_scheduleStatusTone(schedule)}`;
    status.textContent = _scheduleStatusLabel(schedule);
    header.appendChild(status);
  }
  root.appendChild(header);
  if (schedule?.paused_reason && /revok/i.test(schedule.paused_reason)) {
    const revoked = document.createElement('div');
    revoked.className = 'schedules-alert';
    revoked.textContent = 'Paused because the session token was revoked.';
    root.appendChild(revoked);
  } else if (schedule?.last_error) {
    const err = document.createElement('div');
    err.className = 'schedules-alert';
    err.textContent = schedule.last_error;
    root.appendChild(err);
  }
  _renderScheduleForm(root, isNew ? null : schedule);
  if (schedule) _renderScheduleFires(root, schedule);
  detail.appendChild(root);
}

function _updateScheduleFiresView() {
  const schedule = _selectedSchedule();
  if (!schedule) return;
  const current = document.querySelector('.schedules-fires');
  if (!current) return;
  const fragment = document.createElement('div');
  _renderScheduleFires(fragment, schedule);
  const next = fragment.firstElementChild;
  if (next) current.replaceWith(next);
}

function _renderSchedulesModal() {
  _renderSchedulesList();
  _renderSchedulesDetail();
}

function _collectScheduleDraft() {
  const preset = document.querySelector('.schedules-cadence-btn.active')?.dataset.schedulePreset || 'hourly';
  const cronExpr = String(document.getElementById('schedules-cron-input')?.value || '').trim();
  return {
    label: String(document.getElementById('schedules-label-input')?.value || '').trim(),
    command: String(document.getElementById('schedules-command-input')?.value || '').trim(),
    cadence_preset: preset === 'custom' ? '' : preset,
    cron_expr: preset === 'custom' ? cronExpr : SCHEDULES_PRESETS[preset],
    timezone: String(document.getElementById('schedules-timezone-input')?.value || 'UTC').trim(),
    enabled: !!document.getElementById('schedules-enabled-input')?.checked,
  };
}

function _syncScheduleDraftFromForm() {
  const data = _collectScheduleDraft();
  _schedulesState.draft = {
    id: _schedulesState.draft?.id || _schedulesState.selectedId || '',
    label: data.label,
    command_text: data.command,
    cadence_preset: data.cadence_preset || 'custom',
    cron_expr: data.cron_expr || SCHEDULES_DEFAULT_CRON,
    timezone: data.timezone || 'UTC',
    enabled: data.enabled,
  };
}

async function _loadSchedulePreview({ immediate = false } = {}) {
  window.clearTimeout(_schedulesState.previewTimer);
  const run = async () => {
    if (!document.getElementById('schedules-form')) return;
    _syncScheduleDraftFromForm();
    const draft = _schedulesState.draft || {};
    const params = new URLSearchParams();
    if (draft.cadence_preset && draft.cadence_preset !== 'custom') params.set('cadence_preset', draft.cadence_preset);
    else params.set('cron', draft.cron_expr || SCHEDULES_DEFAULT_CRON);
    params.set('tz', draft.timezone || 'UTC');
    _schedulesState.preview = { ..._schedulesState.preview, loading: true, error: '' };
    _updateSchedulePreviewView();
    try {
      const data = await _scheduleJson(`/schedules/preview?${params.toString()}`, { cache: 'no-store' });
      _schedulesState.preview = {
        loading: false,
        error: '',
        next_fires: Array.isArray(data.next_fires) ? data.next_fires : [],
        cron_expr: data.cron_expr || draft.cron_expr || SCHEDULES_DEFAULT_CRON,
        timezone: data.timezone || draft.timezone || 'UTC',
      };
    } catch (err) {
      _schedulesState.preview = {
        ..._schedulesState.preview,
        loading: false,
        error: err?.message || 'Could not preview cadence',
        next_fires: [],
      };
    }
    _updateSchedulePreviewView();
  };
  if (immediate) {
    await run();
  } else {
    _schedulesState.previewTimer = window.setTimeout(run, 250);
  }
}

async function _loadScheduleFires(scheduleId, { offset = 0 } = {}) {
  if (!scheduleId) return;
  _schedulesState.loadingFires = true;
  _updateScheduleFiresView();
  try {
    const params = new URLSearchParams({
      limit: String(SCHEDULES_FIRES_LIMIT),
      offset: String(Math.max(0, Number(offset || 0))),
    });
    const data = await _scheduleJson(
      `/schedules/${encodeURIComponent(scheduleId)}/fires?${params.toString()}`,
      { cache: 'no-store' },
    );
    _schedulesState.fires = Array.isArray(data.fires) ? data.fires : [];
    _schedulesState.firesMeta = {
      limit: Number(data.limit || SCHEDULES_FIRES_LIMIT),
      offset: Number(data.offset || 0),
      total: Number(data.total || 0),
      has_more: !!data.has_more,
    };
  } catch (err) {
    _schedulesState.fires = [];
    _schedulesState.firesMeta = { limit: SCHEDULES_FIRES_LIMIT, offset: 0, total: 0, has_more: false };
    _scheduleToast(err?.message || 'Could not load schedule fires', 'error');
  } finally {
    _schedulesState.loadingFires = false;
    _updateScheduleFiresView();
  }
}

async function refreshSchedulesModal({ selectId = '', command = '' } = {}) {
  _schedulesState.loading = true;
  _renderSchedulesModal();
  try {
    const data = await _scheduleJson('/schedules', { cache: 'no-store' });
    _schedulesState.schedules = Array.isArray(data.schedules) ? data.schedules : [];
    const currentId = String(selectId || _schedulesState.selectedId || '');
    const fallbackId = _schedulesState.schedules[0]?.id || '';
    _schedulesState.selectedId = _schedulesState.schedules.some(item => String(item.id || '') === currentId)
      ? currentId
      : fallbackId;
    if (command) {
      _schedulesState.mode = 'new';
      _schedulesState.selectedId = '';
      _schedulesState.draft = _scheduleDraftFromSchedule(null, command);
    } else if (_schedulesState.selectedId) {
      _schedulesState.mode = 'view';
      _schedulesState.draft = _scheduleDraftFromSchedule(_selectedSchedule());
    }
    _schedulesState.fires = [];
  } catch (err) {
    _scheduleToast(err?.message || 'Could not load schedules', 'error');
  } finally {
    _schedulesState.loading = false;
    _renderSchedulesModal();
    await _loadSchedulePreview({ immediate: true });
    if (_schedulesState.selectedId) await _loadScheduleFires(_schedulesState.selectedId);
  }
}

async function openSchedulesModal(options = {}) {
  const { overlay } = _scheduleEls();
  if (!overlay) return;
  if (typeof _closeMajorOverlays === 'function') _closeMajorOverlays();
  _setSchedulesOpen(true);
  _schedulesState.mode = options.command ? 'new' : 'view';
  _schedulesState.selectedId = String(options.scheduleId || '');
  _schedulesState.draft = options.command ? _scheduleDraftFromSchedule(null, options.command) : null;
  await refreshSchedulesModal({
    selectId: options.scheduleId || '',
    command: options.command || '',
  });
}

async function _saveScheduleForm(event) {
  event?.preventDefault?.();
  const data = _collectScheduleDraft();
  if (!data.command) {
    _scheduleToast('Command is required', 'error');
    return;
  }
  _schedulesState.saving = true;
  _renderSchedulesDetail();
  const selected = _selectedSchedule();
  const isNew = _schedulesState.mode === 'new' || !selected;
  try {
    const url = isNew ? '/schedules' : `/schedules/${encodeURIComponent(selected.id)}`;
    const method = isNew ? 'POST' : 'PATCH';
    const payload = { ...data };
    const response = await _scheduleJson(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const schedule = response.schedule || {};
    _scheduleToast(isNew ? 'Schedule created' : 'Schedule saved');
    _schedulesState.mode = 'view';
    await refreshSchedulesModal({ selectId: schedule.id || selected?.id || '' });
    if (typeof loadScheduleAutocompleteHints === 'function') loadScheduleAutocompleteHints().catch(() => {});
    if (typeof refreshHistoryPanel === 'function') refreshHistoryPanel();
  } catch (err) {
    _scheduleToast(err?.message || 'Could not save schedule', 'error');
  } finally {
    _schedulesState.saving = false;
    _renderSchedulesDetail();
  }
}

async function _deleteSelectedSchedule(schedule) {
  if (!schedule) return;
  let confirmed = true;
  if (typeof showConfirm === 'function') {
    confirmed = await showConfirm({
      title: 'Delete schedule?',
      message: _scheduleTitle(schedule),
      confirmText: 'Delete',
      cancelText: 'Cancel',
      tone: 'danger',
    });
  }
  if (!confirmed) return;
  try {
    await _scheduleJson(`/schedules/${encodeURIComponent(schedule.id)}`, { method: 'DELETE' });
    _scheduleToast('Schedule deleted');
    _schedulesState.selectedId = '';
    await refreshSchedulesModal();
    if (typeof loadScheduleAutocompleteHints === 'function') loadScheduleAutocompleteHints().catch(() => {});
    if (typeof refreshHistoryPanel === 'function') refreshHistoryPanel();
  } catch (err) {
    _scheduleToast(err?.message || 'Could not delete schedule', 'error');
  }
}

async function _patchSelectedSchedule(schedule, updates, successMessage) {
  if (!schedule) return;
  try {
    const response = await _scheduleJson(`/schedules/${encodeURIComponent(schedule.id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    });
    _scheduleToast(successMessage);
    await refreshSchedulesModal({ selectId: response.schedule?.id || schedule.id });
    if (typeof loadScheduleAutocompleteHints === 'function') loadScheduleAutocompleteHints().catch(() => {});
    if (typeof refreshHistoryPanel === 'function') refreshHistoryPanel();
  } catch (err) {
    _scheduleToast(err?.message || 'Could not update schedule', 'error');
  }
}

async function _runSelectedSchedule(schedule) {
  if (!schedule) return;
  try {
    const data = await _scheduleJson(`/schedules/${encodeURIComponent(schedule.id)}/run-now`, { method: 'POST' });
    _scheduleToast(data.status === 'fired' ? 'Schedule fired' : 'Schedule skipped');
    await refreshSchedulesModal({ selectId: schedule.id });
    if (typeof refreshHistoryPanel === 'function') refreshHistoryPanel();
  } catch (err) {
    _scheduleToast(err?.message || 'Could not fire schedule', 'error');
  }
}

function _selectSchedule(scheduleId) {
  _schedulesState.mode = 'view';
  _schedulesState.selectedId = String(scheduleId || '');
  _schedulesState.draft = _scheduleDraftFromSchedule(_selectedSchedule());
  _schedulesState.fires = [];
  _renderSchedulesModal();
  _loadSchedulePreview({ immediate: true }).catch(() => {});
  _loadScheduleFires(_schedulesState.selectedId).catch(() => {});
}

function _newSchedule(command = '') {
  _schedulesState.mode = 'new';
  _schedulesState.selectedId = '';
  _schedulesState.draft = _scheduleDraftFromSchedule(null, command);
  _schedulesState.fires = [];
  _renderSchedulesModal();
  _loadSchedulePreview({ immediate: true }).catch(() => {});
}

function _bindSchedulesModal() {
  const { overlay, newBtn, refreshBtn } = _scheduleEls();
  if (!overlay) return;
  overlay.addEventListener('click', (event) => {
    if (event.target === overlay) {
      closeSchedulesModal();
      return;
    }
    const close = event.target.closest?.('.schedules-close');
    if (close) {
      closeSchedulesModal();
      return;
    }
    const row = event.target.closest?.('[data-schedule-id]');
    if (row) {
      _selectSchedule(row.dataset.scheduleId || '');
      return;
    }
    const preset = event.target.closest?.('[data-schedule-preset]');
    if (preset) {
      event.preventDefault();
      const value = preset.dataset.schedulePreset || 'hourly';
      _setScheduleCadencePreset(value);
      const cronInput = document.getElementById('schedules-cron-input');
      if (cronInput && value !== 'custom') cronInput.value = SCHEDULES_PRESETS[value] || SCHEDULES_DEFAULT_CRON;
      _loadSchedulePreview().catch(() => {});
      return;
    }
    const action = event.target.closest?.('[data-schedule-action]');
    if (action) {
      event.preventDefault();
      const schedule = _selectedSchedule();
      const value = action.dataset.scheduleAction;
      if (value === 'delete') _deleteSelectedSchedule(schedule);
      if (value === 'pause') _patchSelectedSchedule(schedule, { enabled: false, paused_reason: 'paused' }, 'Schedule paused');
      if (value === 'resume') _patchSelectedSchedule(schedule, { enabled: true, paused_reason: '' }, 'Schedule resumed');
      if (value === 'run-now') _runSelectedSchedule(schedule);
      if (value === 'refresh-fires') _loadScheduleFires(schedule?.id || '').catch(() => {});
      return;
    }
    const page = event.target.closest?.('[data-schedule-fires-page]');
    if (page) {
      const meta = _schedulesState.firesMeta || {};
      const direction = page.dataset.scheduleFiresPage;
      const nextOffset = direction === 'next'
        ? Number(meta.offset || 0) + Number(meta.limit || SCHEDULES_FIRES_LIMIT)
        : Math.max(0, Number(meta.offset || 0) - Number(meta.limit || SCHEDULES_FIRES_LIMIT));
      _loadScheduleFires(_schedulesState.selectedId, { offset: nextOffset }).catch(() => {});
      return;
    }
    const run = event.target.closest?.('[data-schedule-run-id]');
    if (run) {
      closeSchedulesModal({ refocus: false });
      if (typeof openHistoryRunDetails === 'function') {
        openHistoryRunDetails({ id: run.dataset.scheduleRunId || '', command: run.dataset.scheduleRunId || '' });
      }
    }
  });
  overlay.addEventListener('input', (event) => {
    if (event.target?.id !== 'schedules-cron-input') return;
    _setScheduleCadencePreset('custom');
    _loadSchedulePreview().catch(() => {});
  });
  overlay.addEventListener('change', (event) => {
    if (event.target?.id !== 'schedules-timezone-input') return;
    _loadSchedulePreview().catch(() => {});
  });
  overlay.addEventListener('submit', (event) => {
    if (event.target && event.target.id === 'schedules-form') _saveScheduleForm(event);
  });
  newBtn?.addEventListener('click', () => _newSchedule());
  refreshBtn?.addEventListener('click', () => refreshSchedulesModal({ selectId: _schedulesState.selectedId }));
  if (typeof bindDismissible === 'function') {
    bindDismissible(overlay, {
      level: 'modal',
      isOpen: isSchedulesOverlayOpen,
      onClose: closeSchedulesModal,
      closeButtons: overlay.querySelectorAll('.schedules-close'),
    });
  }
}

document.addEventListener('DOMContentLoaded', _bindSchedulesModal);

window.openSchedulesModal = openSchedulesModal;
window.closeSchedulesModal = closeSchedulesModal;
window.isSchedulesOverlayOpen = isSchedulesOverlayOpen;
