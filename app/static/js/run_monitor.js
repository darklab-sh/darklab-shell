// ── App-native active run monitor ──
// HUD-attached drawer on desktop, bottom sheet on mobile. The terminal `runs`
// command remains authoritative; this surface is an inspection companion.

(function () {
  let monitorEl = null;
  let scrimEl = null;
  let listEl = null;
  let summaryEl = null;
  let pollTimer = null;
  let tickTimer = null;
  let isOpen = false;

  const POLL_MS = 3000;
  const STATUS_AFFORDANCE_PULSE_KEY = 'run_monitor_status_affordance_seen';
  const resourceStateByRunId = new Map();

  function _isMobileRunMonitor() {
    return window.matchMedia && window.matchMedia('(max-width: 600px)').matches;
  }

  function _formatElapsed(started) {
    const start = Date.parse(String(started || ''));
    if (!Number.isFinite(start)) return '-';
    const total = Math.max(0, Math.floor((Date.now() - start) / 1000));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = total % 60;
    return [hours, minutes, seconds].map(value => String(value).padStart(2, '0')).join(':');
  }

  function _shortRunId(run) {
    return String(run?.run_id || run?.id || '').slice(0, 8) || '-';
  }

  function _formatCpuPercent(value) {
    if (value === null || value === undefined) return 'n/a';
    if (!Number.isFinite(Number(value))) return 'collecting';
    const cpu = Math.min(100, Math.max(0, Number(value)));
    return `${cpu.toFixed(cpu >= 10 ? 0 : 1)}%`;
  }

  function _isTelemetryNumber(value) {
    return value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));
  }

  function _runResourceUsage(run) {
    const runId = String(run?.run_id || run?.id || '');
    const usage = run?.resource_usage && typeof run.resource_usage === 'object'
      ? run.resource_usage
      : {};
    const previous = runId ? resourceStateByRunId.get(runId) : null;
    const now = Date.now();
    const cpuSeconds = _isTelemetryNumber(usage.cpu_seconds)
      ? Number(usage.cpu_seconds)
      : null;
    let cpuPercent = previous?.cpu_percent;
    if (cpuSeconds !== null && previous && _isTelemetryNumber(previous.cpu_seconds)) {
      const elapsedSeconds = Math.max(0, (now - Number(previous.sampled_at || now)) / 1000);
      const deltaCpu = cpuSeconds - Number(previous.cpu_seconds);
      if (elapsedSeconds > 0 && deltaCpu >= 0) {
        cpuPercent = (deltaCpu / elapsedSeconds) * 100;
      }
    }
    const memoryBytes = _isTelemetryNumber(usage.memory_bytes)
      ? Number(usage.memory_bytes)
      : previous?.memory_bytes;
    const resolved = {
      cpu_percent: cpuPercent,
      cpu_seconds: cpuSeconds ?? previous?.cpu_seconds,
      memory_bytes: memoryBytes,
      sampled_at: cpuSeconds !== null ? now : previous?.sampled_at,
    };
    if (runId && (
      _isTelemetryNumber(resolved.cpu_percent)
      || _isTelemetryNumber(resolved.cpu_seconds)
      || _isTelemetryNumber(resolved.memory_bytes)
    )) {
      resourceStateByRunId.set(runId, resolved);
    }
    return resolved;
  }

  function _formatMemoryBytes(value) {
    if (value === null || value === undefined) return 'n/a';
    const bytes = Number(value);
    if (!Number.isFinite(bytes) || bytes < 0) return '-';
    const units = ['B', 'KB', 'MB', 'GB'];
    let size = bytes;
    let unitIndex = 0;
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex += 1;
    }
    const precision = unitIndex === 0 || size >= 10 ? 0 : 1;
    return `${size.toFixed(precision)} ${units[unitIndex]}`;
  }

  function _memoryPercent(value) {
    if (!_isTelemetryNumber(value)) return null;
    const gibibyte = 1024 * 1024 * 1024;
    return Math.min(100, Math.max(0, (Number(value) / gibibyte) * 100));
  }

  function _meterPercent(value) {
    if (!_isTelemetryNumber(value)) return 0;
    return Math.min(100, Math.max(0, Number(value)));
  }

  function _runMonitorMeter({ label, value, percent, className = '' }) {
    const meter = document.createElement('div');
    meter.className = `run-monitor-meter ${className}`.trim();
    meter.style.setProperty('--meter-percent', `${_meterPercent(percent)}%`);
    meter.setAttribute('aria-label', `${label} ${value}`);

    const labelEl = document.createElement('span');
    labelEl.className = 'run-monitor-meter-label';
    labelEl.textContent = label;

    const ring = document.createElement('span');
    ring.className = 'run-monitor-meter-ring';

    const valueEl = document.createElement('span');
    valueEl.className = 'run-monitor-meter-value';
    valueEl.textContent = value;

    ring.append(valueEl);
    meter.append(labelEl, ring);
    return meter;
  }

  function _tabForRun(run) {
    const runId = String(run?.run_id || run?.id || '');
    const currentTabs = typeof getTabs === 'function' ? getTabs() : [];
    if (!runId || !Array.isArray(currentTabs)) return null;
    return currentTabs.find(candidate => (
      candidate && (candidate.runId === runId || candidate.historyRunId === runId)
    )) || null;
  }

  function _tabLabelForRun(run) {
    const tab = _tabForRun(run);
    if (!tab) return '';
    return String(tab.label || tab.command || tab.id || '').trim();
  }

  function _positionMonitor() {
    const rail = document.getElementById('rail');
    const right = rail ? Math.ceil(rail.getBoundingClientRect().right) : 0;
    const hud = document.getElementById('hud');
    const hudBottom = hud ? Math.ceil(window.innerHeight - hud.getBoundingClientRect().top) : 46;
    document.documentElement.style.setProperty('--run-monitor-left', `${right}px`);
    document.documentElement.style.setProperty('--run-monitor-bottom', `${hudBottom}px`);
  }

  function _updateElapsedTimers() {
    document.querySelectorAll('[data-run-monitor-started]').forEach(el => {
      el.textContent = _formatElapsed(el.getAttribute('data-run-monitor-started'));
    });
  }

  async function _loadActiveRuns() {
    const resp = await apiFetch('/history/active');
    const data = await resp.json();
    if (!resp.ok) throw new Error(data?.error || `HTTP ${resp.status}`);
    return Array.isArray(data?.runs) ? data.runs : [];
  }

  function _ensureMonitor() {
    if (monitorEl && scrimEl && listEl && summaryEl) return;

    scrimEl = document.createElement('div');
    scrimEl.className = 'run-monitor-scrim u-hidden';
    scrimEl.setAttribute('aria-hidden', 'true');
    scrimEl.addEventListener('click', () => closeRunMonitor());

    monitorEl = document.createElement('aside');
    monitorEl.id = 'run-monitor';
    monitorEl.className = 'run-monitor u-hidden';
    monitorEl.setAttribute('role', 'dialog');
    monitorEl.setAttribute('aria-modal', 'false');
    monitorEl.setAttribute('aria-labelledby', 'run-monitor-title');

    const header = document.createElement('div');
    header.className = 'run-monitor-header';

    const titleWrap = document.createElement('div');
    const title = document.createElement('div');
    title.id = 'run-monitor-title';
    title.className = 'run-monitor-title';
    title.textContent = 'Run Monitor';
    summaryEl = document.createElement('div');
    summaryEl.className = 'run-monitor-summary';
    summaryEl.textContent = 'Loading...';
    titleWrap.append(title, summaryEl);

    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'run-monitor-close';
    closeBtn.setAttribute('aria-label', 'Collapse run monitor');
    const closeIcon = document.createElement('span');
    closeIcon.className = 'run-monitor-collapse-glyph';
    closeIcon.setAttribute('aria-hidden', 'true');
    closeIcon.textContent = '»';
    closeBtn.appendChild(closeIcon);
    closeBtn.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      closeRunMonitor();
    });

    header.append(titleWrap, closeBtn);

    listEl = document.createElement('div');
    listEl.className = 'run-monitor-list';

    monitorEl.append(header, listEl);
    monitorEl.addEventListener('click', event => event.stopPropagation());
    document.body.append(scrimEl, monitorEl);
  }

  function _renderRuns(runs) {
    if (!listEl || !summaryEl) return;
    listEl.replaceChildren();
    summaryEl.textContent = runs.length === 1 ? '1 active run' : `${runs.length} active runs`;
    const activeRunIds = new Set(
      runs.map(run => String(run?.run_id || run?.id || '')).filter(Boolean),
    );
    [...resourceStateByRunId.keys()].forEach(runId => {
      if (!activeRunIds.has(runId)) resourceStateByRunId.delete(runId);
    });

    runs.forEach(run => {
      const tab = _tabForRun(run);
      const item = document.createElement('article');
      item.className = 'run-monitor-item';
      item.dataset.runId = String(run?.run_id || run?.id || '');
      if (tab && typeof activateTab === 'function') {
        item.classList.add('run-monitor-item-clickable');
        item.setAttribute('role', 'button');
        item.setAttribute('tabindex', '0');
        item.setAttribute('aria-label', `Open tab for ${String(run?.command || 'active run')}`);
        const openTab = () => {
          activateTab(tab.id, { focusComposer: false });
          closeRunMonitor();
        };
        item.addEventListener('click', openTab);
        item.addEventListener('keydown', event => {
          if (event.key !== 'Enter' && event.key !== ' ') return;
          event.preventDefault();
          openTab();
        });
      }

      const command = document.createElement('div');
      command.className = 'run-monitor-command';
      command.textContent = String(run?.command || '').trim() || '(unknown command)';

      const meta = document.createElement('div');
      meta.className = 'run-monitor-meta';
      const tabLabel = _tabLabelForRun(run);
      const runId = document.createElement('span');
      runId.textContent = `run ${_shortRunId(run)}`;
      const pid = document.createElement('span');
      pid.textContent = `pid ${run?.pid || '-'}`;
      const elapsed = document.createElement('span');
      elapsed.className = 'run-monitor-elapsed';
      elapsed.setAttribute('data-run-monitor-started', String(run?.started || ''));
      elapsed.textContent = _formatElapsed(run?.started);
      meta.append(runId, document.createTextNode(' · '), pid, document.createTextNode(' · '), elapsed);
      if (tabLabel) meta.append(document.createTextNode(' · '), document.createTextNode(tabLabel));

      const details = document.createElement('div');
      details.className = 'run-monitor-details';
      details.append(command, meta);

      const usage = _runResourceUsage(run);
      const meters = document.createElement('div');
      meters.className = 'run-monitor-meters';
      meters.append(
        _runMonitorMeter({
          label: 'CPU',
          value: _formatCpuPercent(usage.cpu_percent),
          percent: usage.cpu_percent,
          className: 'run-monitor-meter-cpu',
        }),
        _runMonitorMeter({
          label: 'MEM',
          value: _formatMemoryBytes(usage.memory_bytes),
          percent: _memoryPercent(usage.memory_bytes),
          className: 'run-monitor-meter-mem',
        }),
      );

      item.append(details, meters);
      listEl.appendChild(item);
    });
    _updateElapsedTimers();
  }

  async function refreshRunMonitor() {
    _ensureMonitor();
    try {
      const runs = await _loadActiveRuns();
      _renderRuns(runs);
    } catch (err) {
      if (summaryEl) summaryEl.textContent = 'Unavailable';
      if (listEl) {
        listEl.replaceChildren();
        const error = document.createElement('div');
        error.className = 'run-monitor-empty run-monitor-error';
        error.textContent = err?.message || 'Run monitor failed to load.';
        listEl.appendChild(error);
      }
    }
  }

  function _startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(() => {
      if (isOpen && document.visibilityState === 'visible') void refreshRunMonitor();
    }, POLL_MS);
    if (tickTimer) clearInterval(tickTimer);
    tickTimer = setInterval(() => {
      if (isOpen && document.visibilityState === 'visible') _updateElapsedTimers();
    }, 1000);
  }

  function _stopPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
    if (tickTimer) clearInterval(tickTimer);
    tickTimer = null;
  }

  async function openRunMonitor(options = {}) {
    const source = String(options.source || 'command');
    let runs = [];
    try {
      runs = await _loadActiveRuns();
    } catch (err) {
      if (typeof showToast === 'function') showToast(err?.message || 'Run monitor failed to load', 'error');
      return false;
    }

    _ensureMonitor();
    isOpen = true;
    _positionMonitor();
    document.body.classList.toggle('run-monitor-mobile-open', _isMobileRunMonitor());
    scrimEl?.classList.remove('u-hidden');
    monitorEl?.classList.remove('u-hidden');
    if (monitorEl) monitorEl.dataset.source = source;
    _renderRuns(runs);
    _startPolling();
    return true;
  }

  function closeRunMonitor() {
    isOpen = false;
    _stopPolling();
    document.body.classList.remove('run-monitor-mobile-open');
    scrimEl?.classList.add('u-hidden');
    monitorEl?.classList.add('u-hidden');
  }

  function _makeHudCellOpenMonitor(cell, source, label) {
    if (!cell || cell.dataset.runMonitorTrigger === '1') return;
    cell.dataset.runMonitorTrigger = '1';
    cell.classList.add('hud-cell-clickable');
    cell.setAttribute('role', 'button');
    cell.setAttribute('tabindex', '0');
    cell.setAttribute('aria-haspopup', 'dialog');
    cell.setAttribute('aria-label', label);
    cell.addEventListener('click', () => { void openRunMonitor({ source }); });
    cell.addEventListener('keydown', event => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      void openRunMonitor({ source });
    });
  }

  function _maybePulseStatusAffordance(cell) {
    try {
      if (sessionStorage.getItem(STATUS_AFFORDANCE_PULSE_KEY) === '1') return;
      sessionStorage.setItem(STATUS_AFFORDANCE_PULSE_KEY, '1');
    } catch (_) {
      if (cell.dataset.runMonitorAffordancePulsed === '1') return;
      cell.dataset.runMonitorAffordancePulsed = '1';
    }
    cell.classList.add('hud-status-affordance-pulse');
    window.setTimeout(() => {
      cell.classList.remove('hud-status-affordance-pulse');
    }, 1400);
  }

  function _ensureStatusAffordanceGlyph(cell) {
    let glyph = cell.querySelector('.run-monitor-status-glyph');
    if (glyph) return glyph;
    glyph = document.createElement('span');
    glyph.className = 'run-monitor-status-glyph';
    glyph.setAttribute('aria-hidden', 'true');
    glyph.textContent = '»';
    cell.appendChild(glyph);
    return glyph;
  }

  function _syncStatusAffordance(statusValue = '') {
    const cell = document.getElementById('hud-status-cell');
    if (!cell) return;
    const statusText = String(statusValue || document.getElementById('status')?.textContent || '').trim().toUpperCase();
    const running = statusText === 'RUNNING';
    _ensureStatusAffordanceGlyph(cell);
    cell.classList.toggle('hud-status-expandable', running);
    cell.title = running ? 'Open Run Monitor' : '';
    if (running) _maybePulseStatusAffordance(cell);
  }

  function _bindHudTriggers() {
    _makeHudCellOpenMonitor(
      document.getElementById('hud-status-cell'),
      'status',
      'Open run monitor from status',
    );
    _makeHudCellOpenMonitor(
      document.getElementById('hud-last-exit-cell') || document.getElementById('hud-last-exit')?.closest('.hud-cell'),
      'last-exit',
      'Open run monitor from last exit',
    );
    _makeHudCellOpenMonitor(
      document.getElementById('hud-tabs-cell') || document.getElementById('hud-tabs')?.closest('.hud-cell'),
      'tabs',
      'Open run monitor from tabs',
    );
  }

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && isOpen) closeRunMonitor();
  });
  document.addEventListener('visibilitychange', () => {
    if (isOpen && document.visibilityState === 'visible') void refreshRunMonitor();
  });
  document.addEventListener('app:status-changed', event => {
    _syncStatusAffordance(event?.detail?.status);
  });
  window.addEventListener('resize', () => {
    if (isOpen) _positionMonitor();
  });

  _bindHudTriggers();
  _syncStatusAffordance();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _bindHudTriggers, { once: true });
  }

  window.openRunMonitor = openRunMonitor;
  window.closeRunMonitor = closeRunMonitor;
  window.refreshRunMonitor = refreshRunMonitor;
}());
