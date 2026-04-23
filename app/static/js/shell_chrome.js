// ── Shell chrome controller ──
// Owns the desktop rail (Recent, Workflows, nav) and the bottom HUD.
// Loaded after dom.js, state.js, ui_helpers.js, history.js, tabs.js, app.js, controller.js
// so the helpers and overlays it delegates to are already defined.

(function initShellChrome(global) {
  if (typeof document === 'undefined') return;

  // ── Elements ────────────────────────────────────────────────────
  const rail              = document.getElementById('rail');
  if (!rail) return; // mobile-only DOM build; nothing to do

  const railCollapseBtn   = document.getElementById('rail-collapse-btn');
  const railResizeHandle  = document.getElementById('rail-resize-handle');
  const railSplitArea     = document.getElementById('rail-split-area');
  const railSplitter      = document.getElementById('rail-splitter');
  const railSectionRecent = document.getElementById('rail-section-recent');
  const railRecentBody    = document.getElementById('rail-recent-list');
  const railRecentCount   = document.getElementById('rail-recent-count');
  const railRecentHeader  = document.getElementById('rail-recent-header');
  const railSectionWorkflows = document.getElementById('rail-section-workflows');
  const railWorkflowsBody = document.getElementById('rail-workflows-list');
  const railWorkflowsHeader = document.getElementById('rail-workflows-header');
  const railWorkflowsCount = document.getElementById('rail-workflows-count');
  const railNav           = document.getElementById('rail-nav');

  const hudStatusCell     = document.getElementById('hud-status-cell');
  const hudLastExitEl     = document.getElementById('hud-last-exit');
  const hudTabsEl         = document.getElementById('hud-tabs');
  const hudLatencyEl      = document.getElementById('hud-latency');
  const hudSessionEl      = document.getElementById('hud-session');
  const hudUptimeEl       = document.getElementById('hud-uptime');
  const hudClockEl        = document.getElementById('hud-clock');
  const hudDbEl           = document.getElementById('hud-db');
  const hudRedisEl        = document.getElementById('hud-redis');

  // ── Prefs (cookie-backed) ───────────────────────────────────────
  const PREF_COLLAPSED = 'pref_rail_collapsed';
  const PREF_WIDTH     = 'pref_rail_width';
  const PREF_RECENT    = 'pref_rail_recent_open';
  const PREF_WORKFLOWS = 'pref_rail_workflows_open';

  const MIN_W = 180, MAX_W = 360, DEFAULT_W = 214;
  const MIN_SECTION_H = 80;

  const readBool = (name, dflt) => {
    const v = typeof getPreference === 'function' ? getPreference(name) : '';
    if (v === '1' || v === 'true') return true;
    if (v === '0' || v === 'false') return false;
    return dflt;
  };
  const writePref = (name, value) => {
    if (typeof setPreferenceCookie === 'function') setPreferenceCookie(name, String(value));
  };

  // ── State ────────────────────────────────────────────────────────
  const ui = {
    collapsed: readBool(PREF_COLLAPSED, false),
    railW: (() => {
      const raw = typeof getPreference === 'function' ? parseInt(getPreference(PREF_WIDTH), 10) : NaN;
      return Number.isFinite(raw) ? Math.max(MIN_W, Math.min(MAX_W, raw)) : DEFAULT_W;
    })(),
    recentOpen: readBool(PREF_RECENT, true),
    workflowsOpen: readBool(PREF_WORKFLOWS, true),
    recentHeight: null, // null → auto-size next time Workflows opens
  };

  let allWorkflows = [];

  // ── Layout application ──────────────────────────────────────────
  function applyCollapsed() {
    rail.classList.toggle('rail-collapsed', ui.collapsed);
    rail.style.setProperty('--rail-w', ui.collapsed ? '44px' : `${ui.railW}px`);
    if (railCollapseBtn) {
      railCollapseBtn.textContent = ui.collapsed ? '»' : '«';
      const label = ui.collapsed ? 'Expand sidebar (Alt+\\)' : 'Collapse sidebar (Alt+\\)';
      railCollapseBtn.title = label;
      railCollapseBtn.setAttribute('aria-label', label);
    }
  }

  function applyWidth() {
    if (!ui.collapsed) rail.style.setProperty('--rail-w', `${ui.railW}px`);
  }

  function applySectionsState() {
    if (!railSplitArea) return;
    railSectionRecent?.classList.toggle('closed', !ui.recentOpen);
    railSectionWorkflows?.classList.toggle('closed', !ui.workflowsOpen);

    const bothOpen = ui.recentOpen && ui.workflowsOpen;
    railSplitArea.classList.toggle('both-open', bothOpen);
    railSplitArea.classList.toggle('workflows-closed', !ui.workflowsOpen);
    railSplitArea.classList.toggle('recent-fixed', bothOpen && ui.recentHeight != null);

    if (railSplitter) railSplitter.hidden = !bothOpen;

    if (bothOpen && ui.recentHeight != null) {
      railSplitArea.style.setProperty('--recent-h', `${ui.recentHeight}px`);
    } else {
      railSplitArea.style.removeProperty('--recent-h');
    }
  }

  // ── Collapse ─────────────────────────────────────────────────────
  function setCollapsed(next) {
    ui.collapsed = !!next;
    applyCollapsed();
    writePref(PREF_COLLAPSED, ui.collapsed ? '1' : '0');
  }
  railCollapseBtn?.addEventListener('click', () => setCollapsed(!ui.collapsed));

  // ── Horizontal drag ──────────────────────────────────────────────
  let railDrag = null;
  function beginRailDrag(clientX) {
    railDrag = { startX: clientX, startW: ui.railW };
    rail.classList.add('rail-dragging');
    document.body.style.cursor = 'ew-resize';
    document.body.style.userSelect = 'none';
  }
  railResizeHandle?.addEventListener('mousedown', e => {
    if (ui.collapsed) return;
    e.preventDefault();
    beginRailDrag(e.clientX);
  });

  // ── Splitter drag ────────────────────────────────────────────────
  let splitterDrag = null;
  function beginSplitterDrag(clientY) {
    if (!railSplitArea) return;
    splitterDrag = { rect: railSplitArea.getBoundingClientRect() };
    rail.classList.add('rail-dragging');
    document.body.style.cursor = 'ns-resize';
    document.body.style.userSelect = 'none';
  }
  railSplitter?.addEventListener('mousedown', e => {
    e.preventDefault();
    beginSplitterDrag(e.clientY);
  });

  function clampRecentHeight(pixels) {
    if (!railSplitArea) return pixels;
    const areaH = railSplitArea.getBoundingClientRect().height;
    return Math.max(MIN_SECTION_H, Math.min(areaH - MIN_SECTION_H - 6, pixels));
  }

  window.addEventListener('mousemove', e => {
    if (railDrag) {
      const next = Math.max(MIN_W, Math.min(MAX_W, railDrag.startW + (e.clientX - railDrag.startX)));
      ui.railW = next;
      applyWidth();
    } else if (splitterDrag) {
      const offsetY = e.clientY - splitterDrag.rect.top;
      ui.recentHeight = clampRecentHeight(offsetY);
      applySectionsState();
    }
  });

  window.addEventListener('mouseup', () => {
    if (railDrag) {
      railDrag = null;
      writePref(PREF_WIDTH, ui.railW);
    }
    if (splitterDrag) splitterDrag = null;
    rail.classList.remove('rail-dragging');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  });

  // ── Section toggles ──────────────────────────────────────────────
  // Rail section headers own their open/closed state via bindDisclosure.
  // `panel: null` + `openClass: null` lets applySectionsState stay the sole
  // writer of the `.closed` class on the section element (it has to
  // coordinate both sections plus the splitter and sizing vars, so letting
  // the helper also toggle classes would produce double-writes). The helper
  // still owns aria-expanded on the header and the post-activation focus
  // contract.
  function onRecentToggle(open) {
    ui.recentOpen = open;
    writePref(PREF_RECENT, open ? '1' : '0');
    applySectionsState();
  }
  function onWorkflowsToggle(open) {
    ui.workflowsOpen = open;
    writePref(PREF_WORKFLOWS, open ? '1' : '0');
    if (!open) ui.recentHeight = null; // reset auto-size next open
    applySectionsState();
    if (open && ui.recentOpen && ui.recentHeight == null) {
      // Auto-size Recent: measure Workflows natural height and leave Recent ≥120px.
      requestAnimationFrame(() => {
        if (!railSplitArea || !railWorkflowsBody) return;
        const areaH = railSplitArea.getBoundingClientRect().height;
        const wfH = railWorkflowsBody.scrollHeight || 180;
        const HEADER_H = 28;
        const SPLITTER_H = 6;
        const desiredWorkflowsH = Math.min(wfH + HEADER_H, Math.max(MIN_SECTION_H, areaH - 120));
        const nextRecentH = Math.max(120, areaH - desiredWorkflowsH - SPLITTER_H);
        ui.recentHeight = clampRecentHeight(nextRecentH);
        applySectionsState();
      });
    }
  }

  if (railRecentHeader) {
    bindDisclosure(railRecentHeader, {
      panel: null,
      openClass: null,
      initialOpen: ui.recentOpen,
      onToggle: onRecentToggle,
    });
  }
  if (railWorkflowsHeader) {
    bindDisclosure(railWorkflowsHeader, {
      panel: null,
      openClass: null,
      initialOpen: ui.workflowsOpen,
      onToggle: onWorkflowsToggle,
    });
  }

  // ── Recent list rendering ───────────────────────────────────────
  function renderRailRecent() {
    if (!railRecentBody) return;
    const items = Array.isArray(global.recentPreviewHistory) ? global.recentPreviewHistory : [];
    railRecentBody.replaceChildren();
    if (railRecentCount) railRecentCount.textContent = String(items.length);

    if (!items.length) {
      const empty = document.createElement('div');
      empty.className = 'rail-section-empty';
      empty.textContent = 'no commands yet';
      railRecentBody.appendChild(empty);
      return;
    }
    // Partition starred-first while preserving original recency order within
    // each group. The star toggle lives in the history drawer / mobile sheet
    // (one source of truth); the rail only reflects the state via ordering
    // and an amber left-edge stripe.
    const starred = typeof global._getStarred === 'function' ? global._getStarred() : new Set();
    const ordered = [
      ...items.filter(cmd => starred.has(cmd)),
      ...items.filter(cmd => !starred.has(cmd)),
    ];
    ordered.forEach(cmd => {
      const isStarred = starred.has(cmd);
      const row = document.createElement('button');
      row.type = 'button';
      row.className = 'rail-item' + (isStarred ? ' starred' : '');
      row.title = cmd;
      const text = document.createElement('span');
      text.className = 'rail-item-text';
      text.textContent = cmd;
      row.appendChild(text);
      row.addEventListener('click', () => {
        if (typeof setComposerValue === 'function') {
          setComposerValue(cmd, cmd.length, cmd.length);
        }
        refocusComposerAfterAction({ preventScroll: true });
        if (typeof resetCmdHistoryNav === 'function') resetCmdHistoryNav();
      });
      railRecentBody.appendChild(row);
    });
  }

  // ── Workflows list rendering ────────────────────────────────────
  function renderRailWorkflows(items) {
    allWorkflows = Array.isArray(items) ? items.slice() : [];
    if (railWorkflowsCount) railWorkflowsCount.textContent = String(allWorkflows.length);
    if (!railWorkflowsBody) return;
    railWorkflowsBody.replaceChildren();
    if (!allWorkflows.length) {
      const empty = document.createElement('div');
      empty.className = 'rail-section-empty';
      empty.textContent = 'no workflows';
      railWorkflowsBody.appendChild(empty);
      return;
    }
    allWorkflows.forEach((wf, idx) => {
      const row = document.createElement('button');
      row.type = 'button';
      row.className = 'rail-item';
      const label = wf.title || wf.name || `workflow ${idx + 1}`;
      row.title = [label, wf.description].filter(Boolean).join('\n');
      const glyph = document.createElement('span');
      glyph.className = 'drill-chev';
      glyph.setAttribute('aria-hidden', 'true');
      glyph.textContent = '›';
      const text = document.createElement('span');
      text.className = 'rail-item-text line-clamp-2';
      text.textContent = label;
      row.appendChild(glyph);
      row.appendChild(text);
      row.addEventListener('click', () => openScopedWorkflow(idx));
      railWorkflowsBody.appendChild(row);
    });
  }

  function openScopedWorkflow(idx) {
    const item = allWorkflows[idx];
    if (!item) return;
    if (typeof renderWorkflowItems === 'function') {
      renderWorkflowItems([item], { emitCatalogEvent: false });
    }
    if (typeof openWorkflows === 'function') {
      openWorkflows();
    } else if (typeof showWorkflowsOverlay === 'function') {
      showWorkflowsOverlay();
    }
  }

  // ── Nav menu ─────────────────────────────────────────────────────
  // The visible rail is the desktop source of truth. Route clicks directly
  // into the shared action layer instead of proxying through hidden header
  // buttons.
  railNav?.addEventListener('click', e => {
    const item = e.target.closest?.('[data-action]');
    if (!item) return;
    const action = item.dataset.action;
    if (action === 'diag') return; // native <a> navigation
    e.preventDefault();
    if (action === 'history' && typeof global.toggleHistoryPanelSurface === 'function') {
      global.toggleHistoryPanelSurface();
      return;
    }
    if (action === 'options' && typeof global.openOptions === 'function') {
      global.openOptions();
      return;
    }
    if (action === 'theme' && typeof global.openThemeSelector === 'function') {
      global.openThemeSelector();
      return;
    }
    if (action === 'faq' && typeof global.openFaq === 'function') {
      global.openFaq();
    }
  });

  // ── HUD: status cell toggle (debug affordance; safe no-op elsewhere) ──
  // Clicking the status cell is a design affordance for toggling mock state.
  // In the real app, status is driven by runner.js — leave this inert unless
  // no run is active, so curious users can't desync the runtime.
  hudStatusCell?.addEventListener('click', () => {
    // Intentionally no-op: status reflects runner state and must not be
    // forced from UI. Left in place to preserve cursor affordance.
  });

  // ── HUD action buttons ──────────────────────────────────────────
  // Desktop-only mirror of the per-tab `.terminal-actions` footer. Each
  // button resolves the active tab at click time so no per-tab wiring is
  // needed; the per-tab footer still exists in the DOM for mobile.
  const hudActions = document.getElementById('hud-actions');
  let hudKillBtn = null;

  function _currentTabId() {
    return (typeof getActiveTabId === 'function') ? getActiveTabId() : null;
  }

  function _closeHudSaveMenu() {
    document.querySelectorAll('.hud-save-wrap.open').forEach(w => w.classList.remove('open'));
  }

  function _makeHudBtn(label, action, onClick, cls = 'btn btn-secondary btn-compact', title = '') {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = cls;
    btn.textContent = label;
    if (action) btn.dataset.action = action;
    if (title) btn.title = title;
    // save-menu is a disclosure trigger: suppress auto-refocus so the dropdown
    // retains user attention. Every other HUD button returns focus to the
    // composer after activation.
    const isDisclosure = action === 'save-menu';
    bindPressable(btn, {
      refocusComposer: !isDisclosure,
      onActivate: e => {
        e.preventDefault();
        onClick(e, btn);
      },
    });
    return btn;
  }

  function buildHudActions() {
    if (!hudActions) return;
    hudActions.replaceChildren();

    hudKillBtn = _makeHudBtn('\u25A0 Kill', 'kill', () => {
      const id = _currentTabId();
      if (id && typeof confirmKill === 'function') confirmKill(id);
    }, 'btn btn-destructive btn-compact u-hidden', 'Kill current run');
    hudActions.appendChild(hudKillBtn);

    hudActions.appendChild(_makeHudBtn('share snapshot', 'permalink', () => {
      const id = _currentTabId();
      if (id && typeof permalinkTab === 'function') permalinkTab(id);
    }, 'btn btn-secondary btn-compact', 'Share tab as permalink (Option+P / Alt+P)'));

    hudActions.appendChild(_makeHudBtn('copy', 'copy', () => {
      const id = _currentTabId();
      if (id && typeof copyTab === 'function') copyTab(id);
    }, 'btn btn-secondary btn-compact', 'Copy tab output (Option+Shift+C)'));

    // Save menu — shares .save-menu markup so existing CSS applies.
    const saveWrap = document.createElement('div');
    saveWrap.className = 'hud-save-wrap';
    const saveBtn = _makeHudBtn('save', 'save-menu', () => {
      saveWrap.classList.toggle('open');
    }, 'btn btn-secondary btn-compact', 'Save tab output (txt / html / pdf)');
    const saveMenu = document.createElement('div');
    saveMenu.className = 'save-menu';
    [
      ['Plain text (.txt)',   'save-txt',  () => { const id = _currentTabId(); if (id && typeof saveTab === 'function') saveTab(id); }],
      ['Styled HTML (.html)', 'save-html', () => { const id = _currentTabId(); if (id && typeof exportTabHtml === 'function') exportTabHtml(id); }],
      ['PDF document (.pdf)', 'save-pdf',  () => { const id = _currentTabId(); if (id && typeof exportTabPdf === 'function') exportTabPdf(id); }],
    ].forEach(([label, action, fn]) => {
      const item = document.createElement('button');
      item.type = 'button';
      item.textContent = label;
      item.dataset.action = action;
      bindPressable(item, {
        onActivate: e => {
          e.preventDefault();
          e.stopPropagation();
          saveWrap.classList.remove('open');
          fn();
        },
      });
      saveMenu.appendChild(item);
    });
    saveWrap.appendChild(saveBtn);
    saveWrap.appendChild(saveMenu);
    hudActions.appendChild(saveWrap);

    hudActions.appendChild(_makeHudBtn('clear', 'clear', () => {
      const id = _currentTabId();
      if (!id) return;
      if (typeof cancelWelcome === 'function') cancelWelcome(id);
      if (typeof clearTab === 'function') clearTab(id, { preserveRunState: true });
    }, 'btn btn-secondary btn-compact', 'Clear active tab (Ctrl+L)'));

    bindOutsideClickClose(saveWrap, {
      triggers: saveBtn,
      isOpen: () => saveWrap.classList.contains('open'),
      onClose: () => _closeHudSaveMenu(),
    });
  }

  function _setHudKillVisible(show) {
    if (!hudKillBtn) return;
    hudKillBtn.classList.toggle('u-hidden', !show);
  }

  function refreshHudActions(tabId) {
    const id = tabId || _currentTabId();
    const tab = (typeof getTab === 'function') ? getTab(id) : null;
    _setHudKillVisible(!!(tab && tab.st === 'running'));
  }

  buildHudActions();

  // ── HUD metrics ─────────────────────────────────────────────────
  // Live-updating pills on the left side of the HUD. State is owned here;
  // setters are exposed on `global` so runner.js and session.js can push in.
  const STATUS_POLL_VISIBLE_MS = 3000;
  const STATUS_POLL_HIDDEN_MS  = 15000;
  const CLOCK_TICK_MS          = 1000;
  const LAT_WARN_MS            = 250;
  const LAT_BAD_MS             = 500;

  const hudState = {
    lastExit: null,     // number | 'killed' | null
    latencyMs: null,    // number | null
    serverUptime: null, // seconds as reported by /status
    serverUptimeAt: 0,  // performance.now() when serverUptime was recorded
    db: null,           // 'ok' | 'down' | null
    redis: null,        // 'ok' | 'down' | 'none' | null
  };
  let hudStatusPollTimer = null;

  function _setValueColor(el, variant) {
    if (!el) return;
    el.classList.remove('hud-value-green', 'hud-value-amber', 'hud-value-red', 'hud-muted');
    if (variant) el.classList.add(variant);
  }

  function _formatUptime(totalSeconds) {
    if (!Number.isFinite(totalSeconds) || totalSeconds < 0) return '—';
    const s = Math.floor(totalSeconds);
    if (s < 60) return `${s}s`;
    if (s < 3600) {
      const m = Math.floor(s / 60);
      const r = s % 60;
      return r ? `${m}m ${r}s` : `${m}m`;
    }
    if (s < 86400) {
      const h = Math.floor(s / 3600);
      const m = Math.floor((s % 3600) / 60);
      return m ? `${h}h ${m}m` : `${h}h`;
    }
    const d = Math.floor(s / 86400);
    const h = Math.floor((s % 86400) / 3600);
    return h ? `${d}d ${h}h` : `${d}d`;
  }

  function _formatUtcClock(ms) {
    const d = new Date(Number.isFinite(ms) ? ms : Date.now());
    const pad = n => String(n).padStart(2, '0');
    return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())} UTC`;
  }

  function _formatOffsetLabel(minutesEastOfUtc) {
    const totalMinutes = Number.isFinite(minutesEastOfUtc) ? minutesEastOfUtc : 0;
    if (totalMinutes === 0) return 'UTC';
    const sign = totalMinutes >= 0 ? '+' : '-';
    const absMinutes = Math.abs(totalMinutes);
    const hours = String(Math.floor(absMinutes / 60)).padStart(2, '0');
    const minutes = String(absMinutes % 60).padStart(2, '0');
    return `GMT${sign}${hours}:${minutes}`;
  }

  function _getLocalClockLabel(d) {
    try {
      const tzName = new Intl.DateTimeFormat([], { timeZoneName: 'short' })
        .formatToParts(d)
        .find(part => part.type === 'timeZoneName')
        ?.value
        ?.trim();
      if (tzName && !/^GMT(?:[+-]\d{1,2}(?::\d{2})?)?$/i.test(tzName) && !/^UTC(?:[+-]\d{1,2}(?::\d{2})?)?$/i.test(tzName)) {
        return tzName;
      }
    } catch (_) {
      // Fall through to the numeric offset label below.
    }
    return _formatOffsetLabel(-d.getTimezoneOffset());
  }

  function _formatLocalClock(ms) {
    const d = new Date(Number.isFinite(ms) ? ms : Date.now());
    const pad = n => String(n).padStart(2, '0');
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())} ${_getLocalClockLabel(d)}`;
  }

  function _renderLastExit() {
    if (!hudLastExitEl) return;
    const v = hudState.lastExit;
    const list = Array.isArray(global.tabs) ? global.tabs : [];
    const activeRunning = list.some(t => t && t.id === global.activeTabId && t.st === 'running');
    if (v === null || v === undefined) {
      hudLastExitEl.textContent = '—';
      _setValueColor(hudLastExitEl, 'hud-muted');
    } else if (v === 'killed') {
      hudLastExitEl.textContent = 'KILLED';
      _setValueColor(hudLastExitEl, activeRunning ? 'hud-muted' : 'hud-value-red');
    } else if (v === 0) {
      hudLastExitEl.textContent = '0';
      _setValueColor(hudLastExitEl, activeRunning ? 'hud-muted' : 'hud-value-green');
    } else {
      hudLastExitEl.textContent = String(v);
      _setValueColor(hudLastExitEl, activeRunning ? 'hud-muted' : 'hud-value-red');
    }
  }

  function _renderLatency() {
    if (!hudLatencyEl) return;
    const ms = hudState.latencyMs;
    if (ms === null || ms === undefined) {
      hudLatencyEl.textContent = '— ms';
      _setValueColor(hudLatencyEl, 'hud-muted');
      return;
    }
    hudLatencyEl.textContent = `${Math.round(ms)} ms`;
    if (ms >= LAT_BAD_MS) _setValueColor(hudLatencyEl, 'hud-value-red');
    else if (ms >= LAT_WARN_MS) _setValueColor(hudLatencyEl, 'hud-value-amber');
    else _setValueColor(hudLatencyEl, 'hud-value-green');
  }

  function _renderTabs() {
    if (!hudTabsEl) return;
    const list = Array.isArray(global.tabs) ? global.tabs : [];
    const running = list.reduce((n, t) => n + (t && t.st === 'running' ? 1 : 0), 0);
    const total = list.length;
    if (!total) hudTabsEl.textContent = '0';
    else if (running > 0) hudTabsEl.textContent = `${total} · ${running} active`;
    else hudTabsEl.textContent = String(total);
    _setValueColor(hudTabsEl, running > 0 ? 'hud-value-amber' : 'hud-muted');
  }

  function _renderSession() {
    if (!hudSessionEl) return;
    // Read directly from localStorage: SESSION_ID in session.js is declared
    // with `let` so it is not attached to window; localStorage is the
    // underlying source of truth and updates synchronously across all paths
    // that change the active session token.
    let token = '';
    try { token = localStorage.getItem('session_token') || ''; } catch (_) {}
    if (token && token.startsWith('tok_')) {
      const masked = (typeof maskSessionToken === 'function') ? maskSessionToken(token) : token;
      hudSessionEl.textContent = masked;
      hudSessionEl.title = `Active session token (${masked})`;
      _setValueColor(hudSessionEl, 'hud-value-green');
    } else {
      hudSessionEl.textContent = 'ANON';
      hudSessionEl.title = 'Anonymous UUID session — generate a token in Options to carry history across devices';
      _setValueColor(hudSessionEl, 'hud-muted');
    }
  }

  function _renderUptime() {
    if (!hudUptimeEl) return;
    if (hudState.serverUptime === null) {
      hudUptimeEl.textContent = '—';
      _setValueColor(hudUptimeEl, 'hud-muted');
      return;
    }
    const deltaS = (performance.now() - hudState.serverUptimeAt) / 1000;
    hudUptimeEl.textContent = _formatUptime(hudState.serverUptime + deltaS);
    _setValueColor(hudUptimeEl, null);
  }

  function _renderClock() {
    if (!hudClockEl) return;
    const mode = typeof global.getHudClockPreference === 'function'
      ? global.getHudClockPreference()
      : 'utc';
    const now = Date.now();
    hudClockEl.textContent = mode === 'local' ? _formatLocalClock(now) : _formatUtcClock(now);
    if (mode === 'local') {
      try {
        const zone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'browser local time';
        hudClockEl.title = `Clock: local time (${zone}, ${_getLocalClockLabel(new Date(now))})`;
      } catch (_) {
        hudClockEl.title = 'Clock: local time';
      }
    } else {
      hudClockEl.title = 'Clock: UTC';
    }
    _setValueColor(hudClockEl, null);
  }

  function _renderDb() {
    if (!hudDbEl) return;
    if (hudState.db === 'ok') {
      hudDbEl.textContent = 'ONLINE';
      _setValueColor(hudDbEl, 'hud-value-green');
    } else if (hudState.db === 'down') {
      hudDbEl.textContent = 'OFFLINE';
      _setValueColor(hudDbEl, 'hud-value-red');
    } else {
      hudDbEl.textContent = '—';
      _setValueColor(hudDbEl, 'hud-muted');
    }
  }

  function _renderRedis() {
    if (!hudRedisEl) return;
    if (hudState.redis === 'ok') {
      hudRedisEl.textContent = 'ONLINE';
      _setValueColor(hudRedisEl, 'hud-value-green');
      hudRedisEl.title = 'Redis backend is reachable';
    } else if (hudState.redis === 'down') {
      hudRedisEl.textContent = 'OFFLINE';
      _setValueColor(hudRedisEl, 'hud-value-red');
      hudRedisEl.title = 'Redis configured but unreachable';
    } else if (hudState.redis === 'none') {
      hudRedisEl.textContent = 'N/A';
      _setValueColor(hudRedisEl, 'hud-muted');
      hudRedisEl.title = 'Redis not configured — rate limiting and process tracking run in-process';
    } else {
      hudRedisEl.textContent = '—';
      _setValueColor(hudRedisEl, 'hud-muted');
    }
  }

  async function pollHudStatus() {
    const t0 = performance.now();
    try {
      const resp = await fetch('/status', { cache: 'no-store', credentials: 'same-origin' });
      const t1 = performance.now();
      hudState.latencyMs = t1 - t0;
      if (resp.ok) {
        const data = await resp.json();
        if (typeof data.uptime === 'number') {
          hudState.serverUptime = data.uptime;
          hudState.serverUptimeAt = performance.now();
        }
        if (typeof data.db === 'string')    hudState.db = data.db;
        if (typeof data.redis === 'string') hudState.redis = data.redis;
      }
    } catch (_) {
      hudState.latencyMs = null;
      hudState.db = 'down';
    }
    _renderLatency();
    _renderUptime();
    _renderDb();
    _renderRedis();
  }

  function _currentHudStatusPollMs() {
    return document.visibilityState === 'visible'
      ? STATUS_POLL_VISIBLE_MS
      : STATUS_POLL_HIDDEN_MS;
  }

  function _startHudStatusPoll({ pollNow = false } = {}) {
    if (hudStatusPollTimer) clearInterval(hudStatusPollTimer);
    hudStatusPollTimer = setInterval(pollHudStatus, _currentHudStatusPollMs());
    if (pollNow) pollHudStatus();
  }

  // Cross-tab SESSION_ID changes fire the 'storage' event, so refresh there
  // as well as on every poll (cheap) so token rotations reflect immediately.
  window.addEventListener('storage', e => {
    if (e.key === 'session_token') _renderSession();
  });
  document.addEventListener('visibilitychange', () => {
    _startHudStatusPoll({ pollNow: document.visibilityState === 'visible' });
  });

  if (typeof onUiEvent === 'function') {
    onUiEvent('app:history-rendered', () => {
      try { renderRailRecent(); } catch (_) { /* non-critical */ }
    });
    onUiEvent('app:workflows-rendered', (e) => {
      try { renderRailWorkflows(e.detail && e.detail.items); } catch (_) { /* non-critical */ }
    });
    onUiEvent('app:workflows-closed', () => {
      if (typeof renderWorkflowItems === 'function') {
        try { renderWorkflowItems(allWorkflows); } catch (_) { /* non-critical */ }
      }
    });
    onUiEvent('app:tab-status-changed', () => {
      try { _renderTabs(); } catch (_) { /* non-critical */ }
      try { _renderLastExit(); } catch (_) { /* non-critical */ }
      try { refreshHudActions(); } catch (_) { /* non-critical */ }
    });
    onUiEvent('app:tab-activated', () => {
      try { _renderLastExit(); } catch (_) { /* non-critical */ }
      try { refreshHudActions(); } catch (_) { /* non-critical */ }
    });
    onUiEvent('app:tab-created', () => {
      try { _renderTabs(); } catch (_) { /* non-critical */ }
      try { refreshHudActions(); } catch (_) { /* non-critical */ }
    });
    onUiEvent('app:tab-closed', () => {
      try { _renderTabs(); } catch (_) { /* non-critical */ }
      try { refreshHudActions(); } catch (_) { /* non-critical */ }
    });
    onUiEvent('app:last-exit-changed', (e) => {
      hudState.lastExit = e.detail ? e.detail.value : null;
      try { _renderLastExit(); } catch (_) { /* non-critical */ }
    });
    onUiEvent('app:tab-kill-visibility-changed', (e) => {
      const tabId = e.detail && e.detail.tabId;
      const activeId = (typeof getActiveTabId === 'function') ? getActiveTabId() : null;
      if (tabId !== activeId) return;
      try { _setHudKillVisible(!!(e.detail && e.detail.visible)); } catch (_) { /* non-critical */ }
    });
  }

  // Initial render and pollers.
  _renderLastExit();
  _renderTabs();
  _renderSession();
  _renderClock();
  _renderLatency();
  _renderUptime();
  _renderDb();
  _renderRedis();

  _startHudStatusPoll({ pollNow: true });
  setInterval(() => { _renderClock(); _renderUptime(); _renderSession(); }, CLOCK_TICK_MS);

  // ── Init ─────────────────────────────────────────────────────────
  applyCollapsed();
  applyWidth();
  applySectionsState();
  renderRailRecent();
  refreshHudActions();

  // Expose the workflows renderer for controller.js to call after /workflows loads.
  global.renderHudClock = _renderClock;
  global.toggleRailCollapsed = () => setCollapsed(!ui.collapsed);

})(globalThis);
