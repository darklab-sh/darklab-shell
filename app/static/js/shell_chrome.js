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

  const hud               = document.getElementById('hud');
  const hudLastExitEl     = document.getElementById('hud-last-exit');
  const hudTabsEl         = document.getElementById('hud-tabs');
  const hudLatencyEl      = document.getElementById('hud-latency');
  const hudSessionEl      = document.getElementById('hud-session');
  const hudProjectCell    = document.getElementById('hud-project-cell');
  const hudProjectEl      = document.getElementById('hud-project');
  const hudUptimeEl       = document.getElementById('hud-uptime');
  const hudClockEl        = document.getElementById('hud-clock');
  const hudDbEl           = document.getElementById('hud-db');
  const hudRedisEl        = document.getElementById('hud-redis');
  const mobileProjectRow  = document.getElementById('mobile-menu-project-row');
  const mobileProjectName = document.getElementById('mobile-menu-project-name');
  const projectWorkspaceOverlay = document.getElementById('project-workspace-overlay');
  const projectWorkspaceModal = document.getElementById('project-workspace-modal');
  const projectWorkspaceBody = document.getElementById('project-workspace-body');
  const projectExplorerBody = document.getElementById('project-explorer-body');
  const projectWorkspaceSubtitle = document.getElementById('project-workspace-subtitle');
  const projectWorkspaceCreateForm = document.getElementById('project-workspace-create-form');
  const projectWorkspaceNameInput = document.getElementById('project-workspace-name');
  const projectTargetEditorOverlay = document.getElementById('project-target-editor-overlay');
  const projectTargetEditorTitle = document.getElementById('project-target-editor-title');
  const projectTargetCreateForm = document.getElementById('project-target-create-form');
  const projectTargetTypeSelect = document.getElementById('project-target-type');
  const projectTargetValueInput = document.getElementById('project-target-value');
  const projectTargetValueHelp = document.getElementById('project-target-value-help');
  const projectTargetValueError = document.getElementById('project-target-value-error');
  const projectTargetLabelInput = document.getElementById('project-target-label');
  const projectTargetNotesInput = document.getElementById('project-target-notes');
  const projectTargetSubmitButton = document.getElementById('project-target-submit');
  const projectNotesForm = document.getElementById('project-notes-form');
  const projectNotesInput = document.getElementById('project-notes-input');
  const projectNotesSaveStatus = document.getElementById('project-notes-save-status');
  const projectWorkspaceMessage = document.getElementById('project-workspace-message');

  // ── Prefs (cookie-backed) ───────────────────────────────────────
  const PREF_COLLAPSED = 'pref_rail_collapsed';
  const PREF_WIDTH     = 'pref_rail_width';
  const PREF_RECENT    = 'pref_rail_recent_open';
  const PREF_WORKFLOWS = 'pref_rail_workflows_open';

  const MIN_W = 180, MAX_W = 360, DEFAULT_W = 214;
  const MIN_SECTION_H = 80;
  const FINDING_REVIEW_STATES = [
    { value: 'new', label: 'New' },
    { value: 'reviewed', label: 'Reviewed' },
    { value: 'important', label: 'Important' },
    { value: 'false_positive', label: 'False positive' },
    { value: 'needs_followup', label: 'Follow-up' },
  ];
  const PROJECT_TARGET_TYPES = [
    { value: 'domain', label: 'domain' },
    { value: 'host', label: 'host' },
    { value: 'ip', label: 'ip' },
    { value: 'cidr', label: 'cidr' },
    { value: 'url', label: 'url' },
    { value: 'port_set', label: 'port set' },
  ];
  const PROJECT_DOMAIN_RE = /^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$/i;
  const PROJECT_HOST_RE = /^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*\.?$/i;
  const PROJECT_IPV4_RE = /^(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)$/;
  const PROJECT_TARGET_VALUE_HELP = {
    domain: {
      placeholder: 'target.example.com',
      help: 'Domain name only. Examples: darklab.sh, api.darklab.sh',
      error: 'Use a domain name, such as darklab.sh or api.darklab.sh.',
    },
    url: {
      placeholder: 'https://target.example.com/path',
      help: 'Full URL including scheme. Examples: https://darklab.sh, https://api.darklab.sh/login',
      error: 'Use a full HTTP or HTTPS URL, such as https://darklab.sh/login.',
    },
    host: {
      placeholder: 'host.example.com',
      help: 'Hostname or IP address. Examples: api.darklab.sh, 192.0.2.10',
      error: 'Use a hostname or IP address, such as api.darklab.sh or 192.0.2.10.',
    },
    ip: {
      placeholder: '192.0.2.10',
      help: 'Single IPv4 or IPv6 address. Examples: 192.0.2.10, 2001:db8::10',
      error: 'Use a single IPv4 or IPv6 address, such as 192.0.2.10 or 2001:db8::10.',
    },
    cidr: {
      placeholder: '192.0.2.0/24',
      help: 'CIDR network range. Examples: 192.0.2.0/24, 2001:db8::/32',
      error: 'Use a CIDR network range, such as 192.0.2.0/24 or 2001:db8::/32.',
    },
    port_set: {
      placeholder: '80,443,8000-8080',
      help: 'Ports or ranges separated by commas. Examples: 80,443 or 8000-8080',
      error: 'Use ports or ranges separated by commas, such as 80,443 or 8000-8080.',
    },
  };

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
  let activeProject = null;
  let projectWorkspaceRows = [];
  let projectWorkspaceSummaries = new Map();
  let projectWorkspaceFindings = new Map();
  let projectWorkspaceLoading = false;
  let projectWorkspaceSelectedId = '';
  let projectWorkspaceTab = 'details';
  let projectWorkspaceFindingsLoadingId = '';
  let projectWorkspaceEditingTargetId = '';
  let projectWorkspaceLastTargetType = 'domain';
  let projectWorkspaceTargetFilters = new Map();
  let projectWorkspaceRunFilters = new Map();
  let projectWorkspaceFindingStatusFilters = new Map();
  let projectWorkspaceCollapsedFindingGroups = new Set();
  let projectNotesSaveTimer = null;
  let projectNotesSaveSeq = 0;
  let projectNotesSavedDelayTimer = null;
  let projectNotesSavedHideTimer = null;
  const PROJECT_NOTES_AUTOSAVE_DELAY_MS = 450;
  const FIELD_SAVED_INDICATOR_DELAY_MS = 200;
  const FIELD_SAVED_INDICATOR_VISIBLE_MS = 1600;

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
    applySectionsState();
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
  // into the shared action layer.
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
    if (action === 'status-monitor' && typeof global.openStatusMonitor === 'function') {
      void global.openStatusMonitor({ source: 'rail' });
      return;
    }
    if (action === 'command-registry' && typeof global.openCommandRegistry === 'function') {
      global.openCommandRegistry();
      return;
    }
    if (action === 'projects' && typeof global.openProjectWorkspace === 'function') {
      void global.openProjectWorkspace();
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
    if (action === 'workspace' && typeof global.openWorkspace === 'function') {
      global.openWorkspace();
      return;
    }
    if (action === 'faq' && typeof global.openFaq === 'function') {
      global.openFaq();
    }
  });

  function _openProjectsFromHud(event) {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    if (typeof global.openProjectWorkspace === 'function') {
      void global.openProjectWorkspace();
    }
  }

  hudProjectCell?.addEventListener('click', _openProjectsFromHud);
  hudProjectCell?.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') _openProjectsFromHud(event);
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
    saveMenu.className = 'save-menu dropdown-surface dropdown-up';
    [
      ['Plain text (.txt)',   'save-txt',  () => { const id = _currentTabId(); if (id && typeof saveTab === 'function') saveTab(id); }],
      ['Styled HTML (.html)', 'save-html', () => { const id = _currentTabId(); if (id && typeof exportTabHtml === 'function') exportTabHtml(id); }],
      ['PDF document (.pdf)', 'save-pdf',  () => { const id = _currentTabId(); if (id && typeof exportTabPdf === 'function') exportTabPdf(id); }],
    ].forEach(([label, action, fn]) => {
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'dropdown-item dropdown-item-compact';
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

  function refreshHudRunningState() {
    if (!hud) return;
    const id = _currentTabId();
    const tab = (typeof getTab === 'function') ? getTab(id) : null;
    hud.classList.toggle('hud-running', !!(tab && tab.st === 'running'));
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
    // Read directly from window storage: SESSION_ID in session.js is declared
    // with `let` so it is not attached to window; localStorage is the
    // underlying source of truth and updates synchronously across all paths
    // that change the active session token.
    let token = '';
    try { token = global.localStorage?.getItem('session_token') || ''; } catch (_) {}
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

  function _projectDisplayName(project) {
    if (!project || typeof project !== 'object') return '';
    return String(project.name || project.slug || project.id || '').trim();
  }

  function _renderActiveProject() {
    const name = _projectDisplayName(activeProject);
    const visible = !!name;
    if (hudProjectCell) hudProjectCell.classList.toggle('u-hidden', !visible);
    if (hudProjectEl) {
      hudProjectEl.textContent = visible ? name : '—';
      hudProjectEl.title = visible ? `Active project: ${name}` : 'No active project';
      _setValueColor(hudProjectEl, visible ? null : 'hud-muted');
    }
    if (mobileProjectRow) mobileProjectRow.classList.toggle('u-hidden', !visible);
    if (mobileProjectName) {
      mobileProjectName.textContent = visible ? name : '';
      mobileProjectName.title = visible ? `Active project: ${name}` : '';
    }
  }

  async function loadActiveProjectContext() {
    if (typeof apiFetch !== 'function') return null;
    try {
      const resp = await apiFetch('/projects/active', { cache: 'no-store' });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      activeProject = data && data.project && typeof data.project === 'object' ? data.project : null;
    } catch (err) {
      activeProject = null;
      if (typeof logClientError === 'function') logClientError('failed to load /projects/active', err);
    }
    _renderActiveProject();
    _syncProjectNotesForm();
    if (typeof emitUiEvent === 'function') {
      emitUiEvent('app:active-project-changed', { project: activeProject });
    }
    return activeProject;
  }

  function _showProjectWorkspaceOverlay() {
    if (!projectWorkspaceOverlay) return;
    projectWorkspaceOverlay.classList.remove('u-hidden');
    projectWorkspaceOverlay.classList.add('open');
    projectWorkspaceOverlay.setAttribute('aria-hidden', 'false');
  }

  function _hideProjectWorkspaceOverlay() {
    if (!projectWorkspaceOverlay) return;
    projectWorkspaceOverlay.classList.add('u-hidden');
    projectWorkspaceOverlay.classList.remove('open');
    projectWorkspaceOverlay.setAttribute('aria-hidden', 'true');
  }

  function isProjectWorkspaceOpen() {
    return !!(projectWorkspaceOverlay && projectWorkspaceOverlay.classList.contains('open'));
  }

  function _setProjectWorkspaceMessage(text = '', { error = false } = {}) {
    if (!projectWorkspaceMessage) return;
    projectWorkspaceMessage.textContent = text;
    projectWorkspaceMessage.classList.toggle('u-hidden', !text);
    projectWorkspaceMessage.classList.toggle('is-error', !!error);
  }

  function _selectedProject() {
    const selectedId = String(projectWorkspaceSelectedId || '');
    if (!selectedId) return null;
    const summary = projectWorkspaceSummaries.get(selectedId);
    if (summary && summary.project && typeof summary.project === 'object') return summary.project;
    return projectWorkspaceRows.find(project => String(project.id || '') === selectedId) || null;
  }

  function _projectSummary(projectId = projectWorkspaceSelectedId) {
    return projectWorkspaceSummaries.get(String(projectId || '')) || null;
  }

  function _ensureSelectedProject() {
    const projectIds = projectWorkspaceRows.map(project => String(project.id || '')).filter(Boolean);
    if (projectWorkspaceSelectedId && projectIds.includes(projectWorkspaceSelectedId)) return;
    const activeId = activeProject && activeProject.id ? String(activeProject.id) : '';
    projectWorkspaceSelectedId = activeId && projectIds.includes(activeId) ? activeId : (projectIds[0] || '');
  }

  function _projectCounts(summary) {
    return summary && summary.counts && typeof summary.counts === 'object' ? summary.counts : {};
  }

  function _projectCountEntries(summary) {
    const counts = _projectCounts(summary);
    return [
      { id: 'runs', label: 'runs', value: counts.runs, tab: 'runs' },
      { id: 'findings', label: 'findings', value: counts.findings, tab: 'findings' },
      { id: 'artifacts', label: 'artifacts', value: counts.artifacts, tab: 'artifacts' },
      { id: 'targets', label: 'targets', value: counts.targets, tab: 'details' },
      { id: 'packages', label: 'packages', value: counts.packages, tab: 'packages' },
      { id: 'notes', label: 'notes', value: counts.annotations, tab: 'details' },
    ].map(item => ({ ...item, value: Number(item.value || 0) }));
  }

  function _projectTargetItems(summary) {
    return summary && Array.isArray(summary.targets) ? summary.targets : [];
  }

  function _projectTargetById(summary, targetId) {
    const normalized = String(targetId || '').trim();
    if (!normalized) return null;
    return _projectTargetItems(summary).find(item => String(item && item.id || '') === normalized) || null;
  }

  function _projectTargetFilterLabel(target) {
    if (!target) return 'target';
    const type = String(target.type || 'target').trim() || 'target';
    const value = String(target.value || '').trim();
    return value ? `${type}: ${value}` : type;
  }

  function _targetFilterableProjectTab() {
    return ['runs', 'findings', 'artifacts'].includes(projectWorkspaceTab);
  }

  function _projectTargetFilterSet(projectId = projectWorkspaceSelectedId) {
    const normalized = String(projectId || '');
    if (!normalized) return new Set();
    let filters = projectWorkspaceTargetFilters.get(normalized);
    if (!filters) {
      filters = new Set();
      projectWorkspaceTargetFilters.set(normalized, filters);
    }
    return filters;
  }

  function _projectTargetFilterIds(projectId = projectWorkspaceSelectedId, summary = _projectSummary(projectId)) {
    const available = new Set(_projectTargetItems(summary).map(target => String(target && target.id || '')).filter(Boolean));
    const filters = _projectTargetFilterSet(projectId);
    [...filters].forEach((targetId) => {
      if (!available.has(targetId)) filters.delete(targetId);
    });
    return [...filters];
  }

  function _projectTargetFilterActive(projectId = projectWorkspaceSelectedId, summary = _projectSummary(projectId)) {
    return _projectTargetFilterIds(projectId, summary).length > 0;
  }

  function _projectRunFilterSet(projectId = projectWorkspaceSelectedId) {
    const normalized = String(projectId || '');
    if (!normalized) return new Set();
    let filters = projectWorkspaceRunFilters.get(normalized);
    if (!filters) {
      filters = new Set();
      projectWorkspaceRunFilters.set(normalized, filters);
    }
    return filters;
  }

  function _projectRunFilterIds(projectId = projectWorkspaceSelectedId, summary = _projectSummary(projectId)) {
    const available = new Set(_projectRunItems(summary).map(run => String(run && run.id || '')).filter(Boolean));
    const filters = _projectRunFilterSet(projectId);
    [...filters].forEach((runId) => {
      if (!available.has(runId)) filters.delete(runId);
    });
    return [...filters];
  }

  function _projectRunFilterActive(projectId = projectWorkspaceSelectedId, summary = _projectSummary(projectId)) {
    return _projectRunFilterIds(projectId, summary).length > 0;
  }

  function _projectRunFilterLabel(run) {
    if (!run) return 'run';
    const command = String(run.command || '').trim();
    const shortId = _shortProjectRunId(run.id);
    return `${command || 'Run'}${shortId ? ` (${shortId})` : ''}`;
  }

  function _projectRunFilterChipLabel(run) {
    if (!run) return 'run';
    const command = String(run.command || '').trim() || 'Run';
    if (command.length <= 16) return command;
    return `${command.slice(0, 14).trimEnd()} ...`;
  }

  function _projectFindingStatusFilterSet(projectId = projectWorkspaceSelectedId) {
    const normalized = String(projectId || '');
    if (!normalized) return new Set();
    if (!projectWorkspaceFindingStatusFilters.has(normalized)) {
      projectWorkspaceFindingStatusFilters.set(normalized, new Set());
    }
    return projectWorkspaceFindingStatusFilters.get(normalized);
  }

  function _projectFindingStatusFilterValues(projectId = projectWorkspaceSelectedId) {
    const valid = new Set(FINDING_REVIEW_STATES.map(state => state.value));
    return [..._projectFindingStatusFilterSet(projectId)].filter(value => valid.has(value));
  }

  function _projectFindingStatusFilterActive(projectId = projectWorkspaceSelectedId) {
    return _projectFindingStatusFilterValues(projectId).length > 0;
  }

  function _findingReviewStateLabel(value) {
    const normalized = String(value || '').trim();
    const state = FINDING_REVIEW_STATES.find(item => item.value === normalized);
    return state ? state.label : normalized;
  }

  function _projectFindingGroupKey(projectId, runLabel) {
    return `${String(projectId || '')}\x1f${String(runLabel || '')}`;
  }

  function _projectFindingGroupCollapsed(projectId, runLabel) {
    return projectWorkspaceCollapsedFindingGroups.has(_projectFindingGroupKey(projectId, runLabel));
  }

  function _projectRunItems(summary) {
    return summary && Array.isArray(summary.runs) ? summary.runs : [];
  }

  function _projectRunById(summary, runId) {
    const normalized = String(runId || '');
    if (!normalized) return null;
    return _projectRunItems(summary).find(run => String(run.id || '') === normalized) || null;
  }

  function _shortProjectRunId(runId) {
    return String(runId || '').trim().slice(0, 8);
  }

  function _projectArtifactItems(summary) {
    return summary && Array.isArray(summary.artifacts) ? summary.artifacts : [];
  }

  function _projectArtifactStatus(artifact) {
    const status = String(artifact && artifact.file_status || '').trim();
    if (status === 'available' || status === 'missing' || status === 'changed') return status;
    return artifact && artifact.file_available === false ? 'missing' : 'available';
  }

  function _projectArtifactStatusLabel(artifact) {
    const status = _projectArtifactStatus(artifact);
    if (status === 'changed') return 'changed';
    if (status === 'missing') return 'missing';
    return 'available';
  }

  function _projectArtifactAccessory(projectId, artifact) {
    const wrap = document.createElement('div');
    wrap.className = 'project-artifact-badges';
    const size = document.createElement('span');
    size.className = 'project-explorer-item-badge';
    size.textContent = _formatProjectBytes(artifact.byte_size);
    const status = document.createElement('span');
    status.className = `project-artifact-status is-${_projectArtifactStatus(artifact)}`;
    status.textContent = _projectArtifactStatusLabel(artifact);
    wrap.append(size, status);
    const actions = document.createElement('div');
    actions.className = 'project-artifact-actions';
    const available = _projectArtifactStatus(artifact) !== 'missing';
    [
      ['preview', 'Preview'],
      ['download', 'Download'],
    ].forEach(([actionName, label]) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn btn-secondary btn-compact project-artifact-action';
      btn.dataset.projectAction = `artifact-${actionName}`;
      btn.dataset.projectId = String(projectId || '');
      btn.dataset.artifactId = String(artifact.id || '');
      btn.dataset.artifactPath = String(artifact.workspace_path || '');
      btn.disabled = !available;
      btn.title = available ? label : 'Workspace file is missing';
      btn.textContent = label;
      actions.appendChild(btn);
    });
    wrap.appendChild(actions);
    return wrap;
  }

  function _projectArtifactDetail(artifact) {
    const parts = [
      artifact.kind || 'file',
      artifact.content_type || 'unknown type',
      _formatProjectDate(artifact.created),
    ];
    const status = _projectArtifactStatus(artifact);
    const statusDetail = String(artifact.file_status_detail || '').trim();
    if (status === 'changed') {
      parts.push(`current ${_formatProjectBytes(artifact.current_byte_size)}`);
    } else if (status === 'missing') {
      parts.push(statusDetail || 'workspace file is missing');
    }
    return parts.filter(Boolean).join(' · ');
  }

  function _projectArtifactDownloadName(artifactPath = '', fallback = 'artifact') {
    const name = String(artifactPath || '').split('/').filter(Boolean).pop();
    return name || fallback;
  }

  async function _previewProjectArtifact(projectId, artifactId) {
    const resp = await apiFetch(
      `/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifactId)}/preview`,
      { cache: 'no-store' },
    );
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.error || 'Unable to preview artifact.');
    const artifact = data.artifact || {};
    const showViewer = global && typeof global.showWorkspaceViewer === 'function'
      ? global.showWorkspaceViewer
      : (typeof window !== 'undefined' && typeof window.showWorkspaceViewer === 'function'
          ? window.showWorkspaceViewer
          : null);
    if (!showViewer) throw new Error('File preview is not available.');
    showViewer(
      artifact.workspace_path || 'artifact',
      data.text || '',
      { size: artifact.current_byte_size ?? artifact.byte_size ?? null },
    );
  }

  async function _downloadProjectArtifact(projectId, artifactId, artifactPath = '') {
    const resp = await apiFetch(
      `/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifactId)}/download`,
      { cache: 'no-store' },
    );
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.error || 'Unable to download artifact.');
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = _projectArtifactDownloadName(artifactPath, artifactId || 'artifact');
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    _setProjectWorkspaceMessage('Artifact download started.');
  }

  function _projectPackageItems(summary) {
    return summary && Array.isArray(summary.packages) ? summary.packages : [];
  }

  function _projectFindingItems(projectId = projectWorkspaceSelectedId) {
    return projectWorkspaceFindings.get(String(projectId || '')) || [];
  }

  function _projectFindingsLoaded(projectId = projectWorkspaceSelectedId) {
    return projectWorkspaceFindings.has(String(projectId || ''));
  }

  function _invalidateProjectFindings(projectId = '') {
    const normalized = String(projectId || '');
    if (normalized) {
      projectWorkspaceFindings.delete(normalized);
    } else {
      projectWorkspaceFindings = new Map();
    }
  }

  function _projectTargetLabel(summary, targetId) {
    const normalized = String(targetId || '').trim();
    if (!normalized) return '';
    const target = _projectTargetItems(summary).find(item => String(item && item.id || '') === normalized);
    if (!target) return '';
    const type = String(target.type || 'target').trim() || 'target';
    const value = String(target.value || '').trim();
    return value ? `target ${type}: ${value}` : `target ${type}`;
  }

  function _formatProjectDate(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString();
  }

  function _formatProjectBytes(value) {
    const bytes = Number(value || 0);
    if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    let amount = bytes;
    let unitIndex = 0;
    while (amount >= 1024 && unitIndex < units.length - 1) {
      amount /= 1024;
      unitIndex += 1;
    }
    return `${amount >= 10 || unitIndex === 0 ? amount.toFixed(0) : amount.toFixed(1)} ${units[unitIndex]}`;
  }

  function _emptyProjectPanel(text) {
    const empty = document.createElement('div');
    empty.className = 'project-explorer-empty';
    empty.textContent = text;
    return empty;
  }

  function _projectMetaRow(label, value) {
    const row = document.createElement('div');
    row.className = 'project-explorer-meta-row';
    const key = document.createElement('span');
    key.textContent = label;
    const val = document.createElement('span');
    val.textContent = String(value || '—');
    row.append(key, val);
    return row;
  }

  function _projectItemRow({ title, meta = '', detail = '', badge = '', action = null, accessory = null }) {
    const row = document.createElement(action && !accessory ? 'button' : 'article');
    row.className = 'project-explorer-item';
    let contentHost = row;
    if (action) {
      if (row.tagName === 'BUTTON') row.type = 'button';
      else if (accessory) {
        contentHost = document.createElement('button');
        contentHost.type = 'button';
        contentHost.className = 'project-explorer-item-click-target';
      }
      contentHost.dataset.projectAction = action.action;
      Object.entries(action.dataset || {}).forEach(([key, value]) => {
        contentHost.dataset[key] = value;
      });
    }
    const main = document.createElement('div');
    main.className = 'project-explorer-item-main';
    const heading = document.createElement('div');
    heading.className = 'project-explorer-item-title';
    heading.textContent = String(title || '');
    main.appendChild(heading);
    if (meta) {
      const metaEl = document.createElement('div');
      metaEl.className = 'project-explorer-item-meta';
      metaEl.textContent = meta;
      main.appendChild(metaEl);
    }
    if (detail) {
      const detailEl = document.createElement('div');
      detailEl.className = 'project-explorer-item-detail';
      detailEl.textContent = detail;
      main.appendChild(detailEl);
    }
    contentHost.appendChild(main);
    if (contentHost !== row) row.appendChild(contentHost);
    if (accessory) {
      row.appendChild(accessory);
    } else if (badge) {
      const badgeEl = document.createElement('span');
      badgeEl.className = 'project-explorer-item-badge';
      badgeEl.textContent = badge;
      row.appendChild(badgeEl);
    }
    return row;
  }

  function _findingReviewControl(finding, projectId) {
    const control = document.createElement('select');
    const reviewState = String(finding.review_state || 'new');
    control.className = `form-select form-control-compact project-finding-review review-${reviewState}`;
    control.dataset.projectReviewState = '1';
    control.dataset.projectId = String(projectId || '');
    control.dataset.findingId = String(finding.id || '');
    control.dataset.previousReviewState = reviewState;
    control.setAttribute('aria-label', 'Finding review state');
    FINDING_REVIEW_STATES.forEach(({ value, label }) => {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = label;
      control.appendChild(option);
    });
    control.value = reviewState;
    return control;
  }

  function _setProjectTargetTypeValue(value) {
    if (!projectTargetTypeSelect) return;
    const normalized = String(value || 'domain');
    if (![...projectTargetTypeSelect.options].some(option => option.value === normalized)) {
      const option = document.createElement('option');
      option.value = normalized;
      option.textContent = normalized;
      projectTargetTypeSelect.appendChild(option);
    }
    projectTargetTypeSelect.value = normalized;
    if (typeof global.syncAppSelect === 'function') {
      global.syncAppSelect(projectTargetTypeSelect);
    }
    _syncProjectTargetValueHelp(normalized);
  }

  function _syncProjectTargetValueHelp(type = '') {
    const normalized = String(type || projectTargetTypeSelect?.value || 'domain').trim();
    const copy = PROJECT_TARGET_VALUE_HELP[normalized] || PROJECT_TARGET_VALUE_HELP.domain;
    if (projectTargetValueInput) {
      projectTargetValueInput.placeholder = copy.placeholder;
    }
    if (projectTargetValueHelp) {
      projectTargetValueHelp.textContent = copy.help;
    }
  }

  function _setProjectTargetValueError(message = '') {
    const hasError = !!message;
    if (projectTargetValueInput) {
      projectTargetValueInput.setAttribute('aria-invalid', hasError ? 'true' : 'false');
    }
    if (projectTargetValueError) {
      projectTargetValueError.textContent = message;
      projectTargetValueError.classList.toggle('u-hidden', !hasError);
    }
  }

  function _isValidProjectIpv6Address(value) {
    const candidate = String(value || '').trim();
    if (!candidate || !candidate.includes(':') || /[\s/]/.test(candidate)) return false;
    try {
      return !!new URL(`http://[${candidate}]`).hostname;
    } catch (_) {
      return false;
    }
  }

  function _isValidProjectIpAddress(value) {
    const candidate = String(value || '').trim();
    return PROJECT_IPV4_RE.test(candidate) || _isValidProjectIpv6Address(candidate);
  }

  function _isValidProjectDomain(value) {
    return PROJECT_DOMAIN_RE.test(String(value || '').trim());
  }

  function _isValidProjectHost(value) {
    const candidate = String(value || '').trim();
    if (!candidate || /[:/?#@\s]/.test(candidate)) return _isValidProjectIpAddress(candidate);
    return PROJECT_HOST_RE.test(candidate);
  }

  function _isValidProjectUrl(value) {
    const candidate = String(value || '').trim();
    if (!candidate || /\s/.test(candidate)) return false;
    try {
      const parsed = new URL(candidate);
      return ['http:', 'https:'].includes(parsed.protocol) && !!parsed.hostname;
    } catch (_) {
      return false;
    }
  }

  function _isValidProjectCidr(value) {
    const candidate = String(value || '').trim();
    const parts = candidate.split('/');
    if (parts.length !== 2 || !parts[0] || !/^\d+$/.test(parts[1])) return false;
    const prefix = Number(parts[1]);
    if (!_isValidProjectIpAddress(parts[0])) return false;
    return parts[0].includes(':') ? prefix >= 0 && prefix <= 128 : prefix >= 0 && prefix <= 32;
  }

  function _isValidProjectPortSet(value) {
    const parts = String(value || '').trim().split(',');
    if (!parts.length) return false;
    return parts.every(part => {
      const match = part.trim().match(/^(\d{1,5})(?:\s*-\s*(\d{1,5}))?$/);
      if (!match) return false;
      const start = Number(match[1]);
      const end = Number(match[2] || match[1]);
      return Number.isInteger(start) && Number.isInteger(end)
        && start >= 1 && start <= 65535
        && end >= 1 && end <= 65535
        && start <= end;
    });
  }

  function _projectTargetValueValidationError(type, value) {
    const normalized = String(type || 'domain').trim();
    const candidate = String(value || '').trim();
    if (!candidate) return 'Enter a target value before saving.';
    const validators = {
      domain: _isValidProjectDomain,
      url: _isValidProjectUrl,
      host: _isValidProjectHost,
      ip: _isValidProjectIpAddress,
      cidr: _isValidProjectCidr,
      port_set: _isValidProjectPortSet,
    };
    const validator = validators[normalized] || validators.domain;
    if (validator(candidate)) return '';
    const copy = PROJECT_TARGET_VALUE_HELP[normalized] || PROJECT_TARGET_VALUE_HELP.domain;
    return `The target value does not match the selected type. ${copy.error}`;
  }

  function _projectTargetEditorPayload() {
    return {
      type: String(projectTargetTypeSelect?.value || 'domain').trim() || 'domain',
      value: String(projectTargetValueInput?.value || '').trim(),
      label: String(projectTargetLabelInput?.value || '').trim(),
      notes: String(projectTargetNotesInput?.value || '').trim(),
    };
  }

  function _openProjectTargetEditor(projectId, target = null) {
    const normalizedProjectId = String(projectId || '');
    if (!normalizedProjectId || !projectTargetEditorOverlay || !projectTargetCreateForm) {
      _setProjectWorkspaceMessage('Select or create a project before adding targets.', { error: true });
      return;
    }
    const isEdit = !!(target && target.id);
    projectWorkspaceEditingTargetId = isEdit ? String(target.id || '') : '';
    projectTargetCreateForm.dataset.projectId = normalizedProjectId;
    projectTargetCreateForm.dataset.targetId = projectWorkspaceEditingTargetId;
    _setProjectTargetTypeValue(isEdit ? target.type : projectWorkspaceLastTargetType);
    if (projectTargetValueInput) projectTargetValueInput.value = isEdit ? String(target.value || '') : '';
    if (projectTargetLabelInput) projectTargetLabelInput.value = isEdit ? String(target.label || '') : '';
    if (projectTargetNotesInput) projectTargetNotesInput.value = isEdit ? String(target.notes || '') : '';
    if (projectTargetEditorTitle) projectTargetEditorTitle.textContent = isEdit ? 'EDIT TARGET' : 'NEW TARGET';
    if (projectTargetSubmitButton) projectTargetSubmitButton.textContent = isEdit ? 'Save Target' : 'Add Target';
    _setProjectTargetValueError('');
    projectTargetEditorOverlay.classList.remove('u-hidden');
    projectTargetEditorOverlay.classList.add('open');
    projectTargetEditorOverlay.setAttribute('aria-hidden', 'false');
    window.setTimeout(() => projectTargetValueInput?.focus(), 0);
  }

  function _closeProjectTargetEditor({ clear = true } = {}) {
    if (projectTargetEditorOverlay) {
      projectTargetEditorOverlay.classList.add('u-hidden');
      projectTargetEditorOverlay.classList.remove('open');
      projectTargetEditorOverlay.setAttribute('aria-hidden', 'true');
    }
    if (clear) {
      projectWorkspaceEditingTargetId = '';
      if (projectTargetCreateForm) {
        delete projectTargetCreateForm.dataset.projectId;
        delete projectTargetCreateForm.dataset.targetId;
      }
      _setProjectTargetTypeValue('domain');
      if (projectTargetValueInput) projectTargetValueInput.value = '';
      if (projectTargetLabelInput) projectTargetLabelInput.value = '';
      if (projectTargetNotesInput) projectTargetNotesInput.value = '';
      _setProjectTargetValueError('');
    }
  }

  function isProjectTargetEditorOpen() {
    return !!(projectTargetEditorOverlay && projectTargetEditorOverlay.classList.contains('open'));
  }

  function _projectTargetDisplayRow(projectId, target) {
    const row = document.createElement('article');
    row.className = 'project-target-row';
    const main = document.createElement('div');
    main.className = 'project-target-main';

    const heading = document.createElement('div');
    heading.className = 'project-target-heading';
    const type = document.createElement('span');
    type.className = 'project-target-type';
    type.textContent = String(target.type || 'target');
    const value = document.createElement('span');
    value.className = 'project-target-value';
    value.textContent = String(target.value || '');
    heading.append(type, value);
    main.appendChild(heading);

    const metaParts = [
      String(target.label || '').trim(),
      String(target.notes || '').trim(),
    ].filter(Boolean);
    if (metaParts.length) {
      const meta = document.createElement('div');
      meta.className = 'project-target-meta';
      meta.textContent = metaParts.join(' · ');
      main.appendChild(meta);
    }

    const actions = document.createElement('div');
    actions.className = 'project-target-actions';
    const edit = _makeProjectButton('Edit', 'edit-target', projectId);
    const remove = _makeProjectButton('Remove', 'delete-target', projectId, 'danger');
    const targetId = String(target.id || '');
    [edit, remove].forEach((btn) => {
      btn.dataset.targetId = targetId;
      btn.dataset.targetValue = String(target.value || '');
    });
    actions.append(edit, remove);
    row.append(main, actions);
    return row;
  }

  function _projectRunRemoveControl(projectId, run) {
    const btn = _makeProjectButton('Remove', 'unlink-run', projectId, 'danger');
    btn.dataset.runId = String(run.id || '');
    btn.dataset.runCommand = String(run.command || '');
    return btn;
  }

  function _projectRunFindingCount(projectId, runId) {
    const normalizedRunId = String(runId || '');
    if (!normalizedRunId || !_projectFindingsLoaded(projectId)) return 0;
    return _projectFindingItems(projectId).filter(finding => String(finding && finding.run_id || '') === normalizedRunId).length;
  }

  function _projectRunArtifactCount(summary, runId) {
    const normalizedRunId = String(runId || '');
    if (!normalizedRunId) return 0;
    return _projectArtifactItems(summary).filter(artifact => String(artifact && artifact.run_id || '') === normalizedRunId).length;
  }

  function _projectRunControls(projectId, run, summary) {
    const runId = String(run && run.id || '');
    const wrap = document.createElement('div');
    wrap.className = 'project-run-row-actions';
    [
      ['finding', _projectRunFindingCount(projectId, runId), 'filter-run-findings'],
      ['artifact', _projectRunArtifactCount(summary, runId), 'filter-run-artifacts'],
    ].forEach(([label, count, action]) => {
      const chip = _makeProjectButton(`${count} ${label}${count === 1 ? '' : 's'}`, action, projectId, count ? 'secondary' : 'ghost');
      chip.classList.add('project-run-count-chip');
      chip.disabled = !count;
      chip.dataset.runId = runId;
      chip.dataset.runCommand = String(run.command || '');
      wrap.appendChild(chip);
    });
    const restore = _makeProjectButton('Restore', 'open-run', projectId);
    restore.dataset.runId = runId;
    restore.dataset.runCommand = String(run.command || '');
    wrap.appendChild(restore);
    wrap.appendChild(_projectRunRemoveControl(projectId, run));
    return wrap;
  }

  function _renderProjectTargets(projectId, targets) {
    if (!targets.length) return _emptyProjectPanel('No targets yet.');
    const list = document.createElement('div');
    list.className = 'project-target-list';
    targets.forEach((target) => {
      list.appendChild(_projectTargetDisplayRow(projectId, target));
    });
    return list;
  }

  function _renderProjectTargetFilterControls(container, projectId, summary) {
    if (!_targetFilterableProjectTab()) return;
    const targets = _projectTargetItems(summary);
    if (!targets.length) return;
    const selectedIds = new Set(_projectTargetFilterIds(projectId, summary));
    const wrap = document.createElement('div');
    wrap.className = 'project-target-filter-bar';

    const dropdown = document.createElement('details');
    dropdown.className = 'project-target-filter-menu';
    const summaryEl = document.createElement('summary');
    summaryEl.className = 'btn btn-secondary btn-compact project-target-filter-trigger';
    summaryEl.textContent = selectedIds.size ? `Filter by target (${selectedIds.size})` : 'Filter by target';
    dropdown.appendChild(summaryEl);

    const menu = document.createElement('div');
    menu.className = 'project-target-filter-options';
    targets.forEach((target) => {
      const targetId = String(target && target.id || '');
      if (!targetId) return;
      const label = document.createElement('label');
      label.className = 'project-target-filter-option';
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.value = targetId;
      input.checked = selectedIds.has(targetId);
      input.dataset.projectTargetFilterOption = '1';
      input.dataset.projectId = projectId;
      const mark = document.createElement('span');
      mark.className = 'project-target-filter-check';
      mark.setAttribute('aria-hidden', 'true');
      mark.textContent = '✓';
      const text = document.createElement('span');
      text.className = 'project-target-filter-option-label';
      text.textContent = _projectTargetFilterLabel(target);
      label.append(input, mark, text);
      menu.appendChild(label);
    });
    dropdown.appendChild(menu);
    wrap.appendChild(dropdown);

    if (selectedIds.size) {
      const chips = document.createElement('div');
      chips.className = 'project-target-filter-chips';
      selectedIds.forEach((targetId) => {
        const target = _projectTargetById(summary, targetId);
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'project-target-filter-chip';
        chip.dataset.projectTargetFilterClear = targetId;
        chip.dataset.projectId = projectId;
        chip.textContent = `${_projectTargetFilterLabel(target)} ×`;
        chips.appendChild(chip);
      });
      const clearAll = document.createElement('button');
      clearAll.type = 'button';
      clearAll.className = 'project-target-filter-clear';
      clearAll.dataset.projectTargetFilterClear = 'all';
      clearAll.dataset.projectId = projectId;
      clearAll.textContent = 'Clear all';
      chips.appendChild(clearAll);
      wrap.appendChild(chips);
    }

    container.appendChild(wrap);
  }

  function _renderProjectFindingStatusFilterControls(container, projectId) {
    if (projectWorkspaceTab !== 'findings') return;
    const selected = new Set(_projectFindingStatusFilterValues(projectId));
    const wrap = document.createElement('div');
    wrap.className = 'project-target-filter-bar project-finding-status-filter-bar';

    const dropdown = document.createElement('details');
    dropdown.className = 'project-target-filter-menu project-finding-status-filter-menu';
    const summaryEl = document.createElement('summary');
    summaryEl.className = 'btn btn-secondary btn-compact project-target-filter-trigger';
    summaryEl.textContent = selected.size ? `Filter by status (${selected.size})` : 'Filter by status';
    dropdown.appendChild(summaryEl);

    const menu = document.createElement('div');
    menu.className = 'project-target-filter-options';
    FINDING_REVIEW_STATES.forEach(({ value, label: labelText }) => {
      const label = document.createElement('label');
      label.className = 'project-target-filter-option';
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.value = value;
      input.checked = selected.has(value);
      input.dataset.projectFindingStatusFilterOption = '1';
      input.dataset.projectId = projectId;
      const mark = document.createElement('span');
      mark.className = 'project-target-filter-check';
      mark.setAttribute('aria-hidden', 'true');
      mark.textContent = '✓';
      const text = document.createElement('span');
      text.className = 'project-target-filter-option-label';
      text.textContent = labelText;
      label.append(input, mark, text);
      menu.appendChild(label);
    });
    dropdown.appendChild(menu);
    wrap.appendChild(dropdown);

    if (selected.size) {
      const chips = document.createElement('div');
      chips.className = 'project-target-filter-chips';
      selected.forEach((status) => {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'project-target-filter-chip';
        chip.dataset.projectFindingStatusFilterClear = status;
        chip.dataset.projectId = projectId;
        chip.textContent = `${_findingReviewStateLabel(status)} ×`;
        chips.appendChild(chip);
      });
      const clearAll = document.createElement('button');
      clearAll.type = 'button';
      clearAll.className = 'project-target-filter-clear';
      clearAll.dataset.projectFindingStatusFilterClear = 'all';
      clearAll.dataset.projectId = projectId;
      clearAll.textContent = 'Clear statuses';
      chips.appendChild(clearAll);
      wrap.appendChild(chips);
    }

    container.appendChild(wrap);
  }

  function _projectFilterDropdown(label, count, optionNodes) {
    const dropdown = document.createElement('details');
    dropdown.className = 'project-target-filter-menu project-shared-filter-menu';
    const summaryEl = document.createElement('summary');
    summaryEl.className = 'btn btn-secondary btn-compact project-target-filter-trigger';
    summaryEl.textContent = count ? `${label} (${count})` : label;
    dropdown.appendChild(summaryEl);

    const menu = document.createElement('div');
    menu.className = 'project-target-filter-options';
    if (optionNodes.length) {
      optionNodes.forEach(node => menu.appendChild(node));
    } else {
      const empty = document.createElement('div');
      empty.className = 'project-target-filter-empty';
      empty.textContent = 'No options available';
      menu.appendChild(empty);
    }
    dropdown.appendChild(menu);
    return dropdown;
  }

  function _projectFilterOption({ labelText, value, checked, dataset }) {
    const label = document.createElement('label');
    label.className = 'project-target-filter-option';
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.value = value;
    input.checked = checked;
    Object.entries(dataset || {}).forEach(([key, dataValue]) => {
      input.dataset[key] = dataValue;
    });
    const mark = document.createElement('span');
    mark.className = 'project-target-filter-check';
    mark.setAttribute('aria-hidden', 'true');
    mark.textContent = '✓';
    const text = document.createElement('span');
    text.className = 'project-target-filter-option-label';
    text.textContent = labelText;
    label.append(input, mark, text);
    return label;
  }

  function _projectFilterChip({ projectId, label, value, clearAttr }) {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'project-target-filter-chip';
    chip.dataset.projectId = projectId;
    chip.dataset[clearAttr] = value;
    chip.textContent = `${label} ×`;
    return chip;
  }

  function _renderProjectFilterBar(projectId, summary) {
    const wrap = document.createElement('div');
    wrap.className = 'project-explorer-filter-panel';

    const controls = document.createElement('div');
    controls.className = 'project-explorer-filter-controls';

    const selectedTargets = new Set(_projectTargetFilterIds(projectId, summary));
    const targetOptions = _projectTargetItems(summary).map(target => {
      const targetId = String(target && target.id || '');
      return _projectFilterOption({
        labelText: _projectTargetFilterLabel(target),
        value: targetId,
        checked: selectedTargets.has(targetId),
        dataset: { projectTargetFilterOption: '1', projectId },
      });
    });
    controls.appendChild(_projectFilterDropdown('Filter by target', selectedTargets.size, targetOptions));

    const selectedRuns = new Set(_projectRunFilterIds(projectId, summary));
    const runOptions = _projectRunItems(summary).map(run => {
      const runId = String(run && run.id || '');
      return _projectFilterOption({
        labelText: _projectRunFilterLabel(run),
        value: runId,
        checked: selectedRuns.has(runId),
        dataset: { projectRunFilterOption: '1', projectId },
      });
    });
    controls.appendChild(_projectFilterDropdown('Filter by run', selectedRuns.size, runOptions));

    const selectedStatuses = new Set(_projectFindingStatusFilterValues(projectId));
    const statusOptions = FINDING_REVIEW_STATES.map(({ value, label: labelText }) => _projectFilterOption({
      labelText,
      value,
      checked: selectedStatuses.has(value),
      dataset: { projectFindingStatusFilterOption: '1', projectId },
    }));
    controls.appendChild(_projectFilterDropdown('Filter by status', selectedStatuses.size, statusOptions));
    wrap.appendChild(controls);

    const chips = document.createElement('div');
    chips.className = 'project-target-filter-chips project-explorer-filter-chips';
    selectedTargets.forEach((targetId) => {
      const target = _projectTargetById(summary, targetId);
      chips.appendChild(_projectFilterChip({
        projectId,
        label: `target: ${_projectTargetFilterLabel(target)}`,
        value: targetId,
        clearAttr: 'projectTargetFilterClear',
      }));
    });
    selectedRuns.forEach((runId) => {
      chips.appendChild(_projectFilterChip({
        projectId,
        label: `run: ${_projectRunFilterChipLabel(_projectRunById(summary, runId))}`,
        value: runId,
        clearAttr: 'projectRunFilterClear',
      }));
    });
    selectedStatuses.forEach((status) => {
      chips.appendChild(_projectFilterChip({
        projectId,
        label: `status: ${_findingReviewStateLabel(status)}`,
        value: status,
        clearAttr: 'projectFindingStatusFilterClear',
      }));
    });
    const hasFilters = selectedTargets.size || selectedRuns.size || selectedStatuses.size;
    if (hasFilters) {
      const clearAll = document.createElement('button');
      clearAll.type = 'button';
      clearAll.className = 'project-target-filter-clear';
      clearAll.dataset.projectFilterClearAll = '1';
      clearAll.dataset.projectId = projectId;
      clearAll.textContent = 'Clear filters';
      chips.appendChild(clearAll);
    } else {
      const empty = document.createElement('span');
      empty.className = 'project-explorer-filter-empty';
      empty.textContent = 'No filters applied';
      chips.appendChild(empty);
    }
    wrap.appendChild(chips);
    return wrap;
  }

  function _projectRunDirectTargetIds(run) {
    const ids = new Set();
    const add = value => {
      const normalized = String(value || '').trim();
      if (normalized) ids.add(normalized);
    };
    add(run && run.target_id);
    if (Array.isArray(run && run.target_ids)) run.target_ids.forEach(add);
    if (Array.isArray(run && run.targets)) {
      run.targets.forEach(target => add(target && typeof target === 'object' ? target.id : target));
    }
    return ids;
  }

  function _projectFindingTargetIds(finding) {
    const ids = new Set();
    const add = value => {
      const normalized = String(value || '').trim();
      if (normalized) ids.add(normalized);
    };
    add(finding && finding.target_id);
    if (Array.isArray(finding && finding.target_ids)) finding.target_ids.forEach(add);
    if (Array.isArray(finding && finding.targets)) {
      finding.targets.forEach(target => add(target && typeof target === 'object' ? target.id : target));
    }
    return ids;
  }

  function _projectRunIdsMatchingTargets(projectId, filterIds) {
    const filters = new Set(filterIds);
    const runIds = new Set();
    if (!filters.size) return runIds;
    _projectFindingItems(projectId).forEach((finding) => {
      const targetIds = _projectFindingTargetIds(finding);
      const runId = String(finding && finding.run_id || '');
      if (runId && [...targetIds].some(targetId => filters.has(targetId))) runIds.add(runId);
    });
    return runIds;
  }

  function _projectRunMatchesTargetFilters(run, projectId, filterIds, matchingRunIds) {
    if (!filterIds.length) return true;
    const runId = String(run && run.id || '');
    if (runId && matchingRunIds.has(runId)) return true;
    const directIds = _projectRunDirectTargetIds(run);
    return filterIds.some(targetId => directIds.has(targetId));
  }

  function _filteredProjectRuns(projectId, summary) {
    let runs = _projectRunItems(summary);
    const runIds = new Set(_projectRunFilterIds(projectId, summary));
    if (runIds.size) {
      runs = runs.filter(run => runIds.has(String(run && run.id || '')));
    }
    const filterIds = _projectTargetFilterIds(projectId, summary);
    if (!filterIds.length) return runs;
    const matchingRunIds = _projectRunIdsMatchingTargets(projectId, filterIds);
    return runs.filter(run => _projectRunMatchesTargetFilters(run, projectId, filterIds, matchingRunIds));
  }

  function _filteredProjectFindings(projectId, summary) {
    let findings = _projectFindingItems(projectId);
    const filterIds = new Set(_projectTargetFilterIds(projectId, summary));
    if (filterIds.size) {
      findings = findings.filter(finding => [..._projectFindingTargetIds(finding)].some(targetId => filterIds.has(targetId)));
    }
    const runFilters = new Set(_projectRunFilterIds(projectId, summary));
    if (runFilters.size) {
      findings = findings.filter(finding => runFilters.has(String(finding && finding.run_id || '')));
    }
    const statusFilters = new Set(_projectFindingStatusFilterValues(projectId));
    if (statusFilters.size) {
      findings = findings.filter(finding => statusFilters.has(String(finding && finding.review_state || 'new')));
    }
    return findings;
  }

  function _filteredProjectArtifacts(projectId, summary) {
    let artifacts = _projectArtifactItems(summary);
    const runFilters = new Set(_projectRunFilterIds(projectId, summary));
    if (runFilters.size) {
      artifacts = artifacts.filter(artifact => runFilters.has(String(artifact && artifact.run_id || '')));
    }
    const filterIds = _projectTargetFilterIds(projectId, summary);
    if (!filterIds.length) return artifacts;
    const matchingRunIds = _projectRunIdsMatchingTargets(projectId, filterIds);
    const matchingDirectRunIds = new Set();
    _projectRunItems(summary).forEach((run) => {
      if (_projectRunMatchesTargetFilters(run, projectId, filterIds, matchingRunIds)) {
        const runId = String(run && run.id || '');
        if (runId) matchingDirectRunIds.add(runId);
      }
    });
    return artifacts.filter(artifact => matchingDirectRunIds.has(String(artifact && artifact.run_id || '')));
  }

  function _groupBy(items, keyFn) {
    const grouped = new Map();
    (Array.isArray(items) ? items : []).forEach((item) => {
      const key = String(keyFn(item) || 'Other');
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(item);
    });
    return grouped;
  }

  async function _loadProjectFindings(projectId) {
    const normalized = String(projectId || '');
    if (!normalized || projectWorkspaceFindings.has(normalized) || projectWorkspaceFindingsLoadingId === normalized) return;
    projectWorkspaceFindingsLoadingId = normalized;
    _renderProjectExplorer();
    try {
      const resp = await apiFetch(`/projects/${encodeURIComponent(normalized)}/findings`, { cache: 'no-store' });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      projectWorkspaceFindings.set(normalized, Array.isArray(data.findings) ? data.findings : []);
    } catch (err) {
      projectWorkspaceFindings.set(normalized, []);
      _setProjectWorkspaceMessage('Could not load project findings.', { error: true });
      if (typeof logClientError === 'function') logClientError('failed to load project findings', err);
    } finally {
      projectWorkspaceFindingsLoadingId = '';
      _renderProjectExplorer();
    }
  }

  function _syncProjectForms(project = _selectedProject()) {
    const hasProject = !!(project && project.id);
    const showingDetails = projectWorkspaceTab === 'details';
    if (projectNotesForm) projectNotesForm.classList.toggle('u-hidden', !hasProject || !showingDetails);
    if (projectNotesInput && document.activeElement !== projectNotesInput) {
      projectNotesInput.value = hasProject ? String(project.notes || '') : '';
      projectNotesInput.dataset.projectId = hasProject ? String(project.id || '') : '';
      projectNotesInput.dataset.savedNotes = projectNotesInput.value;
      projectNotesInput.placeholder = hasProject
        ? `Notes for ${_projectDisplayName(project)}`
        : 'Select a project to edit notes';
    }
  }

  function _syncProjectNotesForm() {
    _syncProjectForms();
  }

  function _setProjectNotesSavedIndicator(visible) {
    if (!projectNotesSaveStatus) return;
    projectNotesSaveStatus.classList.toggle('u-hidden', !visible);
  }

  function _hideProjectNotesSavedIndicator() {
    if (projectNotesSavedDelayTimer) {
      clearTimeout(projectNotesSavedDelayTimer);
      projectNotesSavedDelayTimer = null;
    }
    if (projectNotesSavedHideTimer) {
      clearTimeout(projectNotesSavedHideTimer);
      projectNotesSavedHideTimer = null;
    }
    _setProjectNotesSavedIndicator(false);
  }

  function _showProjectNotesSavedIndicator() {
    _hideProjectNotesSavedIndicator();
    projectNotesSavedDelayTimer = setTimeout(() => {
      projectNotesSavedDelayTimer = null;
      _setProjectNotesSavedIndicator(true);
      projectNotesSavedHideTimer = setTimeout(() => {
        projectNotesSavedHideTimer = null;
        _setProjectNotesSavedIndicator(false);
      }, FIELD_SAVED_INDICATOR_VISIBLE_MS);
    }, FIELD_SAVED_INDICATOR_DELAY_MS);
  }

  function _cacheProjectNotes(projectId, notes, updatedProject = null) {
    const normalizedProjectId = String(projectId || '');
    if (!normalizedProjectId) return;
    const replacement = updatedProject && typeof updatedProject === 'object'
      ? updatedProject
      : null;
    projectWorkspaceRows = projectWorkspaceRows.map(project => {
      if (String(project && project.id || '') !== normalizedProjectId) return project;
      return replacement || { ...project, notes };
    });
    if (activeProject && String(activeProject.id || '') === normalizedProjectId) {
      activeProject = replacement || { ...activeProject, notes };
    }
  }

  async function _saveProjectNotesNow({ force = false } = {}) {
    if (!projectNotesInput) return;
    const projectId = String(projectNotesInput.dataset.projectId || projectWorkspaceSelectedId || '');
    if (!projectId) return;
    const notes = String(projectNotesInput.value || '');
    if (!force && notes === String(projectNotesInput.dataset.savedNotes || '')) return;
    const seq = ++projectNotesSaveSeq;
    try {
      const resp = await _projectWorkspaceRequest(`/projects/${encodeURIComponent(projectId)}`, {
        method: 'PUT',
        body: JSON.stringify({ notes }),
      });
      const data = await resp.json();
      const updatedProject = data && data.project && typeof data.project === 'object' ? data.project : null;
      if (seq === projectNotesSaveSeq) {
        projectNotesInput.dataset.savedNotes = notes;
        _showProjectNotesSavedIndicator();
      }
      _cacheProjectNotes(projectId, notes, updatedProject);
      _renderActiveProject();
    } catch (err) {
      _setProjectWorkspaceMessage(err.message || 'Could not save project notes.', { error: true });
    }
  }

  function _scheduleProjectNotesAutosave() {
    if (projectNotesSaveTimer) {
      clearTimeout(projectNotesSaveTimer);
      projectNotesSaveTimer = null;
    }
    projectNotesSaveTimer = setTimeout(() => {
      projectNotesSaveTimer = null;
      _saveProjectNotesNow().catch(() => {});
    }, PROJECT_NOTES_AUTOSAVE_DELAY_MS);
  }

  function _flushProjectNotesAutosave() {
    if (projectNotesSaveTimer) {
      clearTimeout(projectNotesSaveTimer);
      projectNotesSaveTimer = null;
    }
    return _saveProjectNotesNow();
  }

  function _makeProjectButton(label, action, projectId, tone = 'secondary') {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `btn btn-${tone} btn-compact`;
    btn.textContent = label;
    btn.dataset.projectAction = action;
    if (projectId) btn.dataset.projectId = projectId;
    return btn;
  }

  function _projectIsArchived(project) {
    return String(project && project.status || '') === 'archived';
  }

  function _orderedProjectRows(activeId, rows = projectWorkspaceRows) {
    const normalizedActiveId = String(activeId || '');
    return (Array.isArray(rows) ? rows : []).slice().sort((left, right) => {
      const leftId = String(left && left.id || '');
      const rightId = String(right && right.id || '');
      if (leftId === normalizedActiveId && rightId !== normalizedActiveId) return -1;
      if (rightId === normalizedActiveId && leftId !== normalizedActiveId) return 1;
      return _projectDisplayName(left).localeCompare(
        _projectDisplayName(right),
        undefined,
        { sensitivity: 'base', numeric: true },
      );
    });
  }

  function _projectListSection(label) {
    const heading = document.createElement('div');
    heading.className = 'project-workspace-section-label';
    heading.textContent = label;
    return heading;
  }

  function _renderProjectListRow(project, activeId) {
    const projectId = String(project.id || '');
    const summary = _projectSummary(projectId);
    const row = document.createElement('button');
    row.type = 'button';
    row.className = 'project-workspace-row'
      + (projectId === activeId ? ' is-active' : '')
      + (projectId === projectWorkspaceSelectedId ? ' is-selected' : '');
    row.dataset.projectId = projectId;
    row.dataset.projectAction = 'select';

    const main = document.createElement('div');
    main.className = 'project-workspace-main';
    const title = document.createElement('div');
    title.className = 'project-workspace-title-row';
    const name = document.createElement('span');
    name.className = 'project-workspace-name';
    name.textContent = String(project.name || project.slug || projectId);
    title.appendChild(name);
    const statusText = projectId === activeId
      ? 'active'
      : (_projectIsArchived(project) ? 'archived' : '');
    if (statusText) {
      const status = document.createElement('span');
      status.className = 'project-workspace-status' + (projectId === activeId ? ' is-active' : '');
      status.textContent = statusText;
      title.appendChild(status);
    }
    const countsWrap = document.createElement('div');
    countsWrap.className = 'project-workspace-counts';
    _projectCountEntries(summary).slice(0, 4).forEach(item => {
      const chip = document.createElement('span');
      chip.className = 'project-workspace-count';
      chip.textContent = `${item.value} ${item.label}`;
      countsWrap.appendChild(chip);
    });
    main.append(title, countsWrap);
    row.appendChild(main);
    return row;
  }

  function _renderProjectList() {
    if (!projectWorkspaceBody) return;
    projectWorkspaceBody.replaceChildren();
    if (projectWorkspaceLoading) {
      projectWorkspaceBody.appendChild(_emptyProjectPanel('Loading projects...'));
      return;
    }
    if (!projectWorkspaceRows.length) {
      projectWorkspaceBody.appendChild(_emptyProjectPanel('No projects yet. Create one to start grouping related work.'));
      return;
    }
    const activeId = activeProject && activeProject.id ? String(activeProject.id) : '';
    const currentProjects = projectWorkspaceRows.filter(project => !_projectIsArchived(project));
    const archivedProjects = projectWorkspaceRows.filter(project => _projectIsArchived(project));
    const hasArchived = archivedProjects.length > 0;
    if (hasArchived && currentProjects.length) projectWorkspaceBody.appendChild(_projectListSection('Current'));
    _orderedProjectRows(activeId, currentProjects).forEach(project => {
      projectWorkspaceBody.appendChild(_renderProjectListRow(project, activeId));
    });
    if (hasArchived) {
      projectWorkspaceBody.appendChild(_projectListSection('Archived'));
      _orderedProjectRows('', archivedProjects).forEach(project => {
        projectWorkspaceBody.appendChild(_renderProjectListRow(project, activeId));
      });
    }
  }

  function _renderProjectHeader(project, summary) {
    const header = document.createElement('div');
    header.className = 'project-explorer-header';
    const titleWrap = document.createElement('div');
    titleWrap.className = 'project-explorer-title-wrap';
    const title = document.createElement('div');
    title.className = 'project-explorer-title';
    title.textContent = _projectDisplayName(project);
    const meta = document.createElement('div');
    meta.className = 'project-explorer-meta';
    meta.textContent = `${String(project.slug || project.id || '')} · ${String(project.id || '')}`;
    titleWrap.append(title, meta);

    const activeId = activeProject && activeProject.id ? String(activeProject.id) : '';
    const actions = document.createElement('div');
    actions.className = 'project-explorer-actions';
    if (String(project.id || '') === activeId) {
      const pill = document.createElement('span');
      pill.className = 'project-explorer-active-pill';
      pill.textContent = 'active';
      actions.appendChild(pill);
      actions.appendChild(_makeProjectButton('Clear', 'clear', String(project.id || '')));
    } else if (project.status !== 'archived') {
      actions.appendChild(_makeProjectButton('Use as active', 'use', String(project.id || '')));
    }
    if (project.status !== 'archived') {
      actions.appendChild(_makeProjectButton('Archive', 'archive', String(project.id || '')));
    }
    header.append(titleWrap, actions);

    const tabs = document.createElement('div');
    tabs.className = 'project-explorer-tabs';
    const tabCounts = _projectCounts(summary);
    const tabItems = [
      { id: 'details', label: 'Details' },
      { id: 'runs', label: 'Runs', count: tabCounts.runs },
      { id: 'findings', label: 'Findings', count: tabCounts.findings },
      { id: 'artifacts', label: 'Artifacts', count: tabCounts.artifacts },
      { id: 'packages', label: 'Packages', count: tabCounts.packages },
    ];
    tabItems.forEach(({ id, label, count }) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'project-explorer-tab' + (projectWorkspaceTab === id ? ' is-active' : '');
      btn.dataset.projectTab = id;
      btn.textContent = count === undefined ? label : `${label} (${Number(count || 0)})`;
      tabs.appendChild(btn);
    });
    return [header, tabs];
  }

  function _renderProjectDetails(container, project, summary) {
    const meta = document.createElement('div');
    meta.className = 'project-explorer-meta-grid';
    meta.append(
      _projectMetaRow('status', project.status || 'active'),
      _projectMetaRow('created', _formatProjectDate(project.created)),
      _projectMetaRow('updated', _formatProjectDate(project.updated)),
    );
    container.appendChild(meta);

    const targets = _projectTargetItems(summary);
    const projectId = String(project.id || '');
    const targetSection = document.createElement('section');
    targetSection.className = 'project-explorer-section';
    const targetHeading = document.createElement('div');
    targetHeading.className = 'project-explorer-section-heading';
    const targetTitle = document.createElement('h3');
    targetTitle.textContent = 'Targets';
    const targetNew = _makeProjectButton('New', 'new-target', projectId, 'primary');
    targetNew.setAttribute('aria-label', 'Add project target');
    targetHeading.append(targetTitle, targetNew);
    targetSection.appendChild(targetHeading);
    targetSection.appendChild(_renderProjectTargets(projectId, targets));
    container.appendChild(targetSection);

    const notesSection = document.createElement('section');
    notesSection.className = 'project-explorer-section';
    const notesTitle = document.createElement('h3');
    notesTitle.textContent = 'Notes';
    notesSection.appendChild(notesTitle);
    if (projectNotesForm) notesSection.appendChild(projectNotesForm);
    container.appendChild(notesSection);
  }

  function _renderProjectRuns(container, projectId, summary) {
    const allRuns = _projectRunItems(summary);
    const filterActive = _projectTargetFilterActive(projectId, summary);
    if (filterActive && !_projectFindingsLoaded(projectId)) {
      container.appendChild(_emptyProjectPanel('Loading target associations...'));
      return;
    }
    const runs = _filteredProjectRuns(projectId, summary);
    if (!allRuns.length) {
      container.appendChild(_emptyProjectPanel('No linked runs yet.'));
      return;
    }
    if (!runs.length) {
      container.appendChild(_emptyProjectPanel('No linked runs match the selected filters.'));
      return;
    }
    runs.forEach((run) => {
      const exit = run.exit_code === null || run.exit_code === undefined ? 'running' : `exit ${run.exit_code}`;
      container.appendChild(_projectItemRow({
        title: run.command,
        meta: _formatProjectDate(run.started),
        detail: `${exit} · ${Number(run.output_line_count || 0)} output lines · linked ${_formatProjectDate(run.created)}`,
        badge: run.id ? '' : exit,
        accessory: run.id ? _projectRunControls(projectId, run, summary) : null,
        action: run.id ? {
          action: 'filter-run',
          dataset: {
            projectId,
            runId: String(run.id || ''),
            runCommand: String(run.command || ''),
          },
        } : null,
      }));
    });
  }

  function _renderProjectFindings(container, projectId, summary) {
    if (projectWorkspaceFindingsLoadingId === projectId && !projectWorkspaceFindings.has(projectId)) {
      container.appendChild(_emptyProjectPanel('Loading findings...'));
      return;
    }
    const allFindings = _projectFindingItems(projectId);
    const findings = _filteredProjectFindings(projectId, summary);
    if (!allFindings.length) {
      container.appendChild(_emptyProjectPanel('No persisted findings for linked runs yet.'));
      return;
    }
    if (!findings.length) {
      const message = _projectTargetFilterActive(projectId, summary) || _projectFindingStatusFilterActive(projectId)
        ? 'No findings match the selected filters.'
        : 'No persisted findings for linked runs yet.';
      container.appendChild(_emptyProjectPanel(message));
      return;
    }
    _groupBy(findings, finding => finding.run_command || finding.run_id).forEach((items, runLabel) => {
      const group = document.createElement('section');
      group.className = 'project-explorer-group';
      const collapsed = _projectFindingGroupCollapsed(projectId, runLabel);
      group.classList.toggle('is-collapsed', collapsed);
      const title = document.createElement('button');
      title.type = 'button';
      title.className = 'project-explorer-group-toggle';
      title.dataset.projectFindingGroupToggle = '1';
      title.dataset.projectId = projectId;
      title.dataset.projectFindingGroup = runLabel;
      title.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
      const caret = document.createElement('span');
      caret.className = 'project-explorer-group-caret';
      caret.setAttribute('aria-hidden', 'true');
      caret.textContent = '▾';
      const label = document.createElement('span');
      label.className = 'project-explorer-group-title';
      label.textContent = runLabel;
      const count = document.createElement('span');
      count.className = 'project-explorer-group-count';
      count.textContent = `${items.length} finding${items.length === 1 ? '' : 's'}`;
      title.append(caret, label, count);
      group.appendChild(title);
      const body = document.createElement('div');
      body.className = 'project-explorer-group-body';
      body.hidden = collapsed;
      items.forEach((finding) => {
        const lineIndex = Number(finding.line_number);
        const metaParts = [
          finding.scope || 'finding',
          _projectTargetLabel(summary, finding.target_id),
          `line ${finding.line_number || 0}`,
        ].filter(Boolean);
        body.appendChild(_projectItemRow({
          title: finding.title || finding.raw_line,
          meta: metaParts.join(' · '),
          detail: finding.raw_line || '',
          badge: finding.review_state || finding.severity || '',
          accessory: finding.id ? _findingReviewControl(finding, projectId) : null,
          action: finding.run_id ? {
            action: 'open-finding',
            dataset: {
              runId: String(finding.run_id || ''),
              runCommand: String(finding.run_command || ''),
              lineIndex: Number.isInteger(lineIndex) ? String(lineIndex) : '',
            },
          } : null,
        }));
      });
      group.appendChild(body);
      container.appendChild(group);
    });
  }

  function _renderProjectArtifacts(container, projectId, summary) {
    const allArtifacts = _projectArtifactItems(summary);
    const filterActive = _projectTargetFilterActive(projectId, summary);
    if (filterActive && !_projectFindingsLoaded(projectId)) {
      container.appendChild(_emptyProjectPanel('Loading target associations...'));
      return;
    }
    const artifacts = _filteredProjectArtifacts(projectId, summary);
    if (!allArtifacts.length) {
      container.appendChild(_emptyProjectPanel('No run artifacts have been captured for this project yet.'));
      return;
    }
    if (!artifacts.length) {
      container.appendChild(_emptyProjectPanel('No artifacts match the selected targets.'));
      return;
    }
    _groupBy(artifacts, artifact => artifact.run_id).forEach((items, runId) => {
      const group = document.createElement('section');
      group.className = 'project-explorer-group';
      const title = document.createElement('h3');
      const run = _projectRunById(summary, runId);
      const command = String(run?.command || '').trim();
      const shortId = _shortProjectRunId(runId);
      const runLink = document.createElement('button');
      runLink.type = 'button';
      runLink.className = 'project-explorer-group-link';
      runLink.dataset.projectAction = 'open-run';
      runLink.dataset.runId = String(runId || '');
      runLink.dataset.runCommand = command;
      runLink.textContent = `${command || 'Run'}${shortId ? ` (${shortId})` : ''}`;
      title.appendChild(runLink);
      group.appendChild(title);
      items.forEach((artifact) => {
        group.appendChild(_projectItemRow({
          title: artifact.display_name || artifact.workspace_path,
          meta: artifact.workspace_path,
          detail: _projectArtifactDetail(artifact),
          accessory: _projectArtifactAccessory(projectId, artifact),
        }));
      });
      container.appendChild(group);
    });
  }

  function _renderProjectPackages(container, summary) {
    const packages = _projectPackageItems(summary);
    if (!packages.length) {
      container.appendChild(_emptyProjectPanel('No evidence packages yet.'));
      return;
    }
    packages.forEach((pkg) => {
      container.appendChild(_projectItemRow({
        title: pkg.name,
        meta: pkg.include_artifacts ? 'includes artifacts' : 'manifest only',
        detail: pkg.description || `Updated ${_formatProjectDate(pkg.updated)}`,
        badge: pkg.status || 'draft',
      }));
    });
  }

  function _renderProjectExplorer() {
    if (!projectExplorerBody) return;
    projectExplorerBody.replaceChildren();
    _ensureSelectedProject();
    const project = _selectedProject();
    const summary = _projectSummary();
    if (projectWorkspaceLoading) {
      projectExplorerBody.appendChild(_emptyProjectPanel('Loading project explorer...'));
      return;
    }
    if (!project) {
      projectExplorerBody.appendChild(_emptyProjectPanel('Create or select a project to explore related work.'));
      _syncProjectForms(null);
      return;
    }
    _syncProjectForms(project);
    const projectId = String(project.id || '');
    const [header, tabs] = _renderProjectHeader(project, summary);
    projectExplorerBody.append(header, _renderProjectFilterBar(projectId, summary), tabs);
    const content = document.createElement('div');
    content.className = 'project-explorer-tab-panel';
    if (projectWorkspaceTab === 'details') _renderProjectDetails(content, project, summary);
    else if (projectWorkspaceTab === 'runs') _renderProjectRuns(content, projectId, summary);
    else if (projectWorkspaceTab === 'findings') _renderProjectFindings(content, projectId, summary);
    else if (projectWorkspaceTab === 'artifacts') _renderProjectArtifacts(content, projectId, summary);
    else if (projectWorkspaceTab === 'packages') _renderProjectPackages(content, summary);
    projectExplorerBody.appendChild(content);
    if (typeof global.enhanceAppSelects === 'function') {
      global.enhanceAppSelects(content);
    }
    if (
      projectWorkspaceTab === 'findings'
      || ['runs', 'artifacts'].includes(projectWorkspaceTab)
      || _projectTargetFilterActive(projectId, summary)
    ) {
      _loadProjectFindings(projectId).catch(() => {});
    }
  }

  function _renderProjectWorkspace() {
    if (projectWorkspaceSubtitle) {
      const count = projectWorkspaceRows.length;
      projectWorkspaceSubtitle.textContent = count
        ? `${count} project workspace${count === 1 ? '' : 's'} in this session.`
        : 'Select a project to review its targets, runs, findings, artifacts, and packages.';
    }
    _renderProjectList();
    _renderProjectExplorer();
  }

  async function _loadProjectSummaries(projects) {
    const summaries = new Map();
    await Promise.all(projects.map(async (project) => {
      const projectId = String(project.id || '');
      if (!projectId) return;
      try {
        const resp = await apiFetch(`/projects/${encodeURIComponent(projectId)}/summary`, { cache: 'no-store' });
        if (!resp.ok) return;
        summaries.set(projectId, await resp.json());
      } catch (err) {
        if (typeof logClientError === 'function') logClientError('failed to load project summary', err);
      }
    }));
    projectWorkspaceSummaries = summaries;
  }

  async function refreshProjectWorkspace() {
    if (!projectWorkspaceBody || typeof apiFetch !== 'function') return;
    projectWorkspaceLoading = true;
    _renderProjectWorkspace();
    try {
      const [projectsResp] = await Promise.all([
        apiFetch('/projects?include_archived=1', { cache: 'no-store' }),
        loadActiveProjectContext(),
      ]);
      if (!projectsResp.ok) throw new Error(`HTTP ${projectsResp.status}`);
      const data = await projectsResp.json();
      projectWorkspaceRows = Array.isArray(data.projects) ? data.projects : [];
      _invalidateProjectFindings();
      await _loadProjectSummaries(projectWorkspaceRows);
      _ensureSelectedProject();
      _setProjectWorkspaceMessage('');
    } catch (err) {
      projectWorkspaceRows = [];
      projectWorkspaceSummaries = new Map();
      _setProjectWorkspaceMessage('Could not load projects.', { error: true });
      if (typeof logClientError === 'function') logClientError('failed to load /projects', err);
    } finally {
      projectWorkspaceLoading = false;
      _syncProjectNotesForm();
      _renderProjectWorkspace();
    }
  }

  async function openProjectWorkspace() {
    if (!projectWorkspaceOverlay || !projectWorkspaceBody) return;
    if (typeof global._closeMajorOverlays === 'function') global._closeMajorOverlays();
    if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
    _showProjectWorkspaceOverlay();
    if (typeof markInteractionSurfaceReady === 'function') {
      markInteractionSurfaceReady('projects', projectWorkspaceOverlay, projectWorkspaceModal);
    }
    await refreshProjectWorkspace();
    const mobileMode = document.body && document.body.classList.contains('mobile-terminal-mode');
    if (!mobileMode && projectWorkspaceNameInput) {
      window.setTimeout(() => projectWorkspaceNameInput.focus(), 0);
    }
  }

  function closeProjectWorkspace({ refocus = true } = {}) {
    _flushProjectNotesAutosave().catch(() => {});
    _closeProjectTargetEditor();
    _hideProjectWorkspaceOverlay();
    _setProjectWorkspaceMessage('');
    if (refocus && typeof refocusComposerAfterAction === 'function') {
      refocusComposerAfterAction({ defer: true });
    }
  }

  async function _projectWorkspaceRequest(url, options = {}) {
    const resp = await apiFetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      },
    });
    if (!resp.ok) {
      let message = `HTTP ${resp.status}`;
      try {
        const data = await resp.json();
        if (data && data.error) message = data.error;
      } catch (_) {}
      throw new Error(message);
    }
    return resp;
  }

  async function _confirmProjectTargetDelete(targetValue) {
    const label = String(targetValue || 'this target');
    const confirmFn = typeof showConfirm === 'function'
      ? showConfirm
      : (global && typeof global.showConfirm === 'function' ? global.showConfirm : null);
    if (confirmFn) {
      const choice = await confirmFn({
        body: `Remove target ${label}?`,
        tone: 'danger',
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'remove', label: 'Remove', role: 'destructive' },
        ],
      });
      return choice === 'remove';
    }
    if (typeof window !== 'undefined' && typeof window.confirm === 'function') {
      return window.confirm(`Remove target ${label}?`);
    }
    return false;
  }

  async function _confirmProjectRunUnlink(runCommand) {
    const label = String(runCommand || 'this run');
    const confirmFn = typeof showConfirm === 'function'
      ? showConfirm
      : (global && typeof global.showConfirm === 'function' ? global.showConfirm : null);
    if (confirmFn) {
      const choice = await confirmFn({
        body: `Remove run from project: ${label}?`,
        tone: 'danger',
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'remove', label: 'Remove', role: 'destructive' },
        ],
      });
      return choice === 'remove';
    }
    if (typeof window !== 'undefined' && typeof window.confirm === 'function') {
      return window.confirm(`Remove run from project: ${label}?`);
    }
    return false;
  }

  projectWorkspaceCreateForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const name = String(projectWorkspaceNameInput?.value || '').trim();
    if (!name) {
      _setProjectWorkspaceMessage('Project name is required.', { error: true });
      return;
    }
    try {
      const resp = await _projectWorkspaceRequest('/projects', {
        method: 'POST',
        body: JSON.stringify({ name }),
      });
      const data = await resp.json();
      const projectId = data && data.project ? data.project.id : '';
      if (projectId) {
        await _projectWorkspaceRequest('/projects/active', {
          method: 'POST',
          body: JSON.stringify({ project_id: projectId }),
        });
      }
      if (projectId) projectWorkspaceSelectedId = String(projectId);
      projectWorkspaceTab = 'details';
      if (projectWorkspaceNameInput) projectWorkspaceNameInput.value = '';
      _setProjectWorkspaceMessage('Project created and selected.');
      await refreshProjectWorkspace();
    } catch (err) {
      _setProjectWorkspaceMessage(err.message || 'Could not create project.', { error: true });
    }
  });

  projectTargetTypeSelect?.addEventListener('change', () => {
    _syncProjectTargetValueHelp(projectTargetTypeSelect.value);
    _setProjectTargetValueError('');
  });

  projectTargetValueInput?.addEventListener('input', () => {
    _setProjectTargetValueError('');
  });

  projectTargetCreateForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const projectId = String(projectTargetCreateForm.dataset.projectId || projectWorkspaceSelectedId || (activeProject && activeProject.id ? activeProject.id : ''));
    const targetId = String(projectTargetCreateForm.dataset.targetId || '');
    const payload = _projectTargetEditorPayload();
    if (!projectId) {
      _setProjectWorkspaceMessage('Select or create a project before adding targets.', { error: true });
      return;
    }
    const validationError = _projectTargetValueValidationError(payload.type, payload.value);
    if (validationError) {
      _setProjectTargetValueError(validationError);
      projectTargetValueInput?.focus();
      return;
    }
    try {
      const url = targetId
        ? `/projects/${encodeURIComponent(projectId)}/targets/${encodeURIComponent(targetId)}`
        : `/projects/${encodeURIComponent(projectId)}/targets`;
      await _projectWorkspaceRequest(url, {
        method: targetId ? 'PUT' : 'POST',
        body: JSON.stringify(payload),
      });
      projectWorkspaceLastTargetType = payload.type || projectWorkspaceLastTargetType;
      _closeProjectTargetEditor();
      await refreshProjectWorkspace();
      if (typeof loadProjectAutocompleteTargets === 'function') {
        loadProjectAutocompleteTargets().catch(() => {});
      }
      _setProjectWorkspaceMessage(targetId ? 'Target updated.' : 'Target added to selected project.');
    } catch (err) {
      _setProjectWorkspaceMessage(err.message || 'Could not save target.', { error: true });
    }
  });

  projectNotesInput?.addEventListener('input', () => {
    _hideProjectNotesSavedIndicator();
    _scheduleProjectNotesAutosave();
  });

  projectNotesInput?.addEventListener('change', () => {
    _flushProjectNotesAutosave().catch(() => {});
  });

  projectNotesInput?.addEventListener('blur', () => {
    _flushProjectNotesAutosave().catch(() => {});
  });

  projectNotesForm?.addEventListener('submit', (event) => {
    event.preventDefault();
    _flushProjectNotesAutosave().catch(() => {});
  });

  function _setCachedFindingReviewState(projectId, findingId, reviewState) {
    const normalizedProjectId = String(projectId || '');
    const normalizedFindingId = String(findingId || '');
    const findings = projectWorkspaceFindings.get(normalizedProjectId);
    if (!normalizedProjectId || !normalizedFindingId || !Array.isArray(findings)) return;
    projectWorkspaceFindings.set(normalizedProjectId, findings.map(finding => {
      if (String(finding && finding.id || '') !== normalizedFindingId) return finding;
      return { ...finding, review_state: reviewState };
    }));
  }

  projectWorkspaceModal?.addEventListener('change', async (event) => {
    const targetFilterControl = event.target.closest?.('[data-project-target-filter-option]');
    if (targetFilterControl) {
      event.stopPropagation();
      const projectId = String(targetFilterControl.dataset.projectId || projectWorkspaceSelectedId || '');
      const targetId = String(targetFilterControl.value || '');
      if (!projectId || !targetId) return;
      const filters = _projectTargetFilterSet(projectId);
      if (targetFilterControl.checked) filters.add(targetId);
      else filters.delete(targetId);
      _renderProjectExplorer();
      return;
    }
    const runFilterControl = event.target.closest?.('[data-project-run-filter-option]');
    if (runFilterControl) {
      event.stopPropagation();
      const projectId = String(runFilterControl.dataset.projectId || projectWorkspaceSelectedId || '');
      const runId = String(runFilterControl.value || '');
      if (!projectId || !runId) return;
      const filters = _projectRunFilterSet(projectId);
      if (runFilterControl.checked) filters.add(runId);
      else filters.delete(runId);
      _renderProjectExplorer();
      return;
    }
    const statusFilterControl = event.target.closest?.('[data-project-finding-status-filter-option]');
    if (statusFilterControl) {
      event.stopPropagation();
      const projectId = String(statusFilterControl.dataset.projectId || projectWorkspaceSelectedId || '');
      const status = String(statusFilterControl.value || '');
      if (!projectId || !status) return;
      const filters = _projectFindingStatusFilterSet(projectId);
      if (statusFilterControl.checked) filters.add(status);
      else filters.delete(status);
      _renderProjectExplorer();
      return;
    }
    const control = event.target.closest?.('[data-project-review-state]');
    if (!control) return;
    event.preventDefault();
    event.stopPropagation();
    const projectId = String(control.dataset.projectId || '');
    const findingId = String(control.dataset.findingId || '');
    const reviewState = String(control.value || 'new');
    const previousReviewState = String(control.dataset.previousReviewState || 'new');
    _setProjectWorkspaceMessage('');
    _setCachedFindingReviewState(projectId, findingId, reviewState);
    _renderProjectExplorer();
    try {
      await _projectWorkspaceRequest(`/findings/${encodeURIComponent(findingId)}/review`, {
        method: 'PUT',
        body: JSON.stringify({ review_state: reviewState }),
      });
    } catch (err) {
      _setCachedFindingReviewState(projectId, findingId, previousReviewState);
      _renderProjectExplorer();
      _setProjectWorkspaceMessage(err.message || 'Could not update finding review state.', { error: true });
    }
  });

  projectWorkspaceModal?.addEventListener('click', async (event) => {
    if (event.target.closest?.('[data-project-review-state]')) return;
    const findingGroupToggle = event.target.closest?.('[data-project-finding-group-toggle]');
    if (findingGroupToggle) {
      event.preventDefault();
      event.stopPropagation();
      const projectId = String(findingGroupToggle.dataset.projectId || projectWorkspaceSelectedId || '');
      const runLabel = String(findingGroupToggle.dataset.projectFindingGroup || '');
      const key = _projectFindingGroupKey(projectId, runLabel);
      if (projectWorkspaceCollapsedFindingGroups.has(key)) {
        projectWorkspaceCollapsedFindingGroups.delete(key);
      } else {
        projectWorkspaceCollapsedFindingGroups.add(key);
      }
      _renderProjectExplorer();
      return;
    }
    const targetFilterClear = event.target.closest?.('[data-project-target-filter-clear]');
    if (targetFilterClear) {
      event.preventDefault();
      event.stopPropagation();
      const projectId = String(targetFilterClear.dataset.projectId || projectWorkspaceSelectedId || '');
      const targetId = String(targetFilterClear.dataset.projectTargetFilterClear || '');
      const filters = _projectTargetFilterSet(projectId);
      if (targetId === 'all') filters.clear();
      else if (targetId) filters.delete(targetId);
      _renderProjectExplorer();
      return;
    }
    const runFilterClear = event.target.closest?.('[data-project-run-filter-clear]');
    if (runFilterClear) {
      event.preventDefault();
      event.stopPropagation();
      const projectId = String(runFilterClear.dataset.projectId || projectWorkspaceSelectedId || '');
      const runId = String(runFilterClear.dataset.projectRunFilterClear || '');
      const filters = _projectRunFilterSet(projectId);
      if (runId === 'all') filters.clear();
      else if (runId) filters.delete(runId);
      _renderProjectExplorer();
      return;
    }
    const statusFilterClear = event.target.closest?.('[data-project-finding-status-filter-clear]');
    if (statusFilterClear) {
      event.preventDefault();
      event.stopPropagation();
      const projectId = String(statusFilterClear.dataset.projectId || projectWorkspaceSelectedId || '');
      const status = String(statusFilterClear.dataset.projectFindingStatusFilterClear || '');
      const filters = _projectFindingStatusFilterSet(projectId);
      if (status === 'all') filters.clear();
      else if (status) filters.delete(status);
      _renderProjectExplorer();
      return;
    }
    const allFilterClear = event.target.closest?.('[data-project-filter-clear-all]');
    if (allFilterClear) {
      event.preventDefault();
      event.stopPropagation();
      const projectId = String(allFilterClear.dataset.projectId || projectWorkspaceSelectedId || '');
      _projectTargetFilterSet(projectId).clear();
      _projectRunFilterSet(projectId).clear();
      _projectFindingStatusFilterSet(projectId).clear();
      _renderProjectExplorer();
      return;
    }
    const tabBtn = event.target.closest?.('[data-project-tab]');
    if (tabBtn) {
      event.preventDefault();
      await _flushProjectNotesAutosave();
      projectWorkspaceTab = tabBtn.dataset.projectTab || 'details';
      if (projectWorkspaceTab !== 'details') _closeProjectTargetEditor();
      _renderProjectExplorer();
      return;
    }
    const btn = event.target.closest?.('[data-project-action]');
    if (!btn) return;
    if (btn.getAttribute('role') === 'button' && event.target.closest?.('select, input, textarea, a, button')) return;
    event.preventDefault();
    const action = btn.dataset.projectAction || '';
    const projectId = btn.dataset.projectId || '';
    try {
      if (action === 'select') {
        await _flushProjectNotesAutosave();
        projectWorkspaceSelectedId = projectId;
        _closeProjectTargetEditor();
        _setProjectWorkspaceMessage('');
        _renderProjectWorkspace();
        return;
      } else if (action === 'use') {
        await _projectWorkspaceRequest('/projects/active', {
          method: 'POST',
          body: JSON.stringify({ project_id: projectId }),
        });
        _setProjectWorkspaceMessage('Active project updated.');
      } else if (action === 'clear') {
        await _projectWorkspaceRequest('/projects/active', { method: 'DELETE' });
        _setProjectWorkspaceMessage('Active project cleared.');
      } else if (action === 'archive') {
        await _projectWorkspaceRequest(`/projects/${encodeURIComponent(projectId)}`, {
          method: 'PUT',
          body: JSON.stringify({ status: 'archived' }),
        });
        if (activeProject && String(activeProject.id || '') === projectId) {
          await _projectWorkspaceRequest('/projects/active', { method: 'DELETE' });
        }
        _setProjectWorkspaceMessage('Project archived.');
      } else if (action === 'new-target') {
        _setProjectWorkspaceMessage('');
        _openProjectTargetEditor(projectId);
        return;
      } else if (action === 'edit-target') {
        const targetId = String(btn.dataset.targetId || '');
        const summary = projectWorkspaceSummaries.get(String(projectId || ''));
        const target = _projectTargetItems(summary).find(item => String(item.id || '') === targetId);
        if (!target) throw new Error('Target is missing its details.');
        _setProjectWorkspaceMessage('');
        _openProjectTargetEditor(projectId, target);
        return;
      } else if (action === 'delete-target') {
        const targetId = String(btn.dataset.targetId || '');
        if (!projectId || !targetId) throw new Error('Target is missing its identifier.');
        const confirmed = await _confirmProjectTargetDelete(btn.dataset.targetValue || '');
        if (!confirmed) return;
        await _projectWorkspaceRequest(`/projects/${encodeURIComponent(projectId)}/targets/${encodeURIComponent(targetId)}`, {
          method: 'DELETE',
        });
        if (projectWorkspaceEditingTargetId === targetId) projectWorkspaceEditingTargetId = '';
        await refreshProjectWorkspace();
        if (typeof loadProjectAutocompleteTargets === 'function') {
          loadProjectAutocompleteTargets().catch(() => {});
        }
        _setProjectWorkspaceMessage('Target removed.');
        return;
      } else if (action === 'filter-run' || action === 'filter-run-findings' || action === 'filter-run-artifacts') {
        const runId = String(btn.dataset.runId || '').trim();
        if (!projectId || !runId) throw new Error('Run is missing its identifier.');
        const filters = _projectRunFilterSet(projectId);
        filters.clear();
        filters.add(runId);
        if (action === 'filter-run-findings') projectWorkspaceTab = 'findings';
        if (action === 'filter-run-artifacts') projectWorkspaceTab = 'artifacts';
        _renderProjectExplorer();
        return;
      } else if (action === 'open-run') {
        const runId = String(btn.dataset.runId || '').trim();
        if (!runId) throw new Error('Run is missing its identifier.');
        const restore = typeof global.restoreHistoryRunIntoTab === 'function'
          ? global.restoreHistoryRunIntoTab
          : (typeof global.restoreHistoryRun === 'function' ? global.restoreHistoryRun : null);
        if (!restore) throw new Error('History restore is not available.');
        await restore({
          id: runId,
          command: String(btn.dataset.runCommand || ''),
          full_output_available: true,
        }, {
          hidePanelOnSuccess: false,
        });
        closeProjectWorkspace({ refocus: false });
        return;
      } else if (action === 'unlink-run') {
        const runId = String(btn.dataset.runId || '').trim();
        if (!projectId || !runId) throw new Error('Run link is missing its identifier.');
        const confirmed = await _confirmProjectRunUnlink(btn.dataset.runCommand || '');
        if (!confirmed) return;
        await _projectWorkspaceRequest(`/projects/${encodeURIComponent(projectId)}/links`, {
          method: 'DELETE',
          body: JSON.stringify({ entity_type: 'run', entity_id: runId }),
        });
        await refreshProjectWorkspace();
        _setProjectWorkspaceMessage('Run removed from project.');
        return;
      } else if (action === 'open-finding') {
        const runId = String(btn.dataset.runId || '').trim();
        if (!runId) throw new Error('Finding is missing its source run.');
        const lineIndexRaw = String(btn.dataset.lineIndex || '').trim();
        const lineIndex = lineIndexRaw === '' ? null : Number(lineIndexRaw);
        const restore = typeof global.restoreHistoryRunIntoTab === 'function'
          ? global.restoreHistoryRunIntoTab
          : (typeof global.restoreHistoryRun === 'function' ? global.restoreHistoryRun : null);
        if (!restore) throw new Error('History restore is not available.');
        await restore({
          id: runId,
          command: String(btn.dataset.runCommand || ''),
          full_output_available: true,
        }, {
          hidePanelOnSuccess: false,
          highlightLineIndex: Number.isInteger(lineIndex) ? lineIndex : null,
        });
        closeProjectWorkspace({ refocus: false });
        return;
      } else if (action === 'artifact-preview') {
        const artifactId = String(btn.dataset.artifactId || '').trim();
        if (!projectId || !artifactId) throw new Error('Artifact is missing its identifier.');
        await _previewProjectArtifact(projectId, artifactId);
        return;
      } else if (action === 'artifact-download') {
        const artifactId = String(btn.dataset.artifactId || '').trim();
        if (!projectId || !artifactId) throw new Error('Artifact is missing its identifier.');
        await _downloadProjectArtifact(projectId, artifactId, btn.dataset.artifactPath || '');
        return;
      }
      await refreshProjectWorkspace();
    } catch (err) {
      _setProjectWorkspaceMessage(err.message || 'Project action failed.', { error: true });
    }
  });

  projectWorkspaceOverlay?.querySelector('.project-workspace-close')?.addEventListener('click', () => {
    closeProjectWorkspace();
  });

  projectTargetEditorOverlay?.querySelector('.project-target-editor-close')?.addEventListener('click', () => {
    _closeProjectTargetEditor();
  });

  projectTargetEditorOverlay?.querySelector('.project-target-editor-cancel')?.addEventListener('click', () => {
    _closeProjectTargetEditor();
  });

  const bindDismissibleFn = global && typeof global.bindDismissible === 'function'
    ? global.bindDismissible
    : (typeof bindDismissible === 'function' ? bindDismissible : null);
  if (bindDismissibleFn && projectTargetEditorOverlay) {
    bindDismissibleFn(projectTargetEditorOverlay, {
      level: 'modal',
      isOpen: isProjectTargetEditorOpen,
      onClose: () => _closeProjectTargetEditor(),
      closeButtons: null,
    });
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
      if (hudState.redis !== 'none') hudState.redis = 'down';
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
    if (e.key === 'session_token') {
      _renderSession();
      loadActiveProjectContext().catch(() => {});
    }
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
      try { refreshHudRunningState(); } catch (_) { /* non-critical */ }
    });
    onUiEvent('app:tab-activated', () => {
      try { _renderLastExit(); } catch (_) { /* non-critical */ }
      try { refreshHudActions(); } catch (_) { /* non-critical */ }
      try { refreshHudRunningState(); } catch (_) { /* non-critical */ }
    });
    onUiEvent('app:tab-created', () => {
      try { _renderTabs(); } catch (_) { /* non-critical */ }
      try { refreshHudActions(); } catch (_) { /* non-critical */ }
      try { refreshHudRunningState(); } catch (_) { /* non-critical */ }
    });
    onUiEvent('app:tab-closed', () => {
      try { _renderTabs(); } catch (_) { /* non-critical */ }
      try { refreshHudActions(); } catch (_) { /* non-critical */ }
      try { refreshHudRunningState(); } catch (_) { /* non-critical */ }
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
  _renderActiveProject();
  refreshHudRunningState();

  _startHudStatusPoll({ pollNow: true });
  setInterval(() => { _renderClock(); _renderUptime(); _renderSession(); }, CLOCK_TICK_MS);

  // ── Init ─────────────────────────────────────────────────────────
  applyCollapsed();
  applyWidth();
  applySectionsState();
  renderRailRecent();
  refreshHudActions();
  loadActiveProjectContext().catch(() => {});

  // Expose the workflows renderer for controller.js to call after /workflows loads.
  global.renderHudClock = _renderClock;
  global.toggleRailCollapsed = () => setCollapsed(!ui.collapsed);
  global.getActiveProjectContext = () => activeProject;
  global.refreshActiveProjectContext = loadActiveProjectContext;
  global.openProjectWorkspace = openProjectWorkspace;
  global.closeProjectWorkspace = closeProjectWorkspace;
  global.isProjectWorkspaceOpen = isProjectWorkspaceOpen;
  global.closeProjectTargetEditor = _closeProjectTargetEditor;
  global.isProjectTargetEditorOpen = isProjectTargetEditorOpen;
  global.refreshProjectWorkspace = refreshProjectWorkspace;

})(globalThis);
