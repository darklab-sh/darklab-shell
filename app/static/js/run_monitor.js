// ── App-native active run monitor ──
// Small HUD drawer on desktop, bottom sheet on mobile. The terminal `runs`
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
    document.documentElement.style.setProperty('--run-monitor-left', `${right}px`);
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
    closeBtn.setAttribute('aria-label', 'Close run monitor');
    closeBtn.textContent = '×';
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

      item.append(command, meta);
      listEl.appendChild(item);
    });
    _updateElapsedTimers();
  }

  async function refreshRunMonitor() {
    _ensureMonitor();
    try {
      const runs = await _loadActiveRuns();
      if (!runs.length) {
        closeRunMonitor();
        return;
      }
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
    const toastOnEmpty = options.toastOnEmpty !== false && source !== 'command';
    let runs = [];
    try {
      runs = await _loadActiveRuns();
    } catch (err) {
      if (typeof showToast === 'function') showToast(err?.message || 'Run monitor failed to load', 'error');
      return false;
    }
    if (!runs.length) {
      closeRunMonitor();
      if (toastOnEmpty && typeof showToast === 'function') showToast('No active runs');
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
  window.addEventListener('resize', () => {
    if (isOpen) _positionMonitor();
  });

  _bindHudTriggers();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _bindHudTriggers, { once: true });
  }

  window.openRunMonitor = openRunMonitor;
  window.closeRunMonitor = closeRunMonitor;
  window.refreshRunMonitor = refreshRunMonitor;
}());
