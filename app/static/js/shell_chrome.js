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
  const projectPackageManifestOverlay = document.getElementById('project-package-manifest-overlay');
  const projectPackageManifestTitle = document.getElementById('project-package-manifest-title');
  const projectPackageManifestJson = document.getElementById('project-package-manifest-json');
  const projectPackageWizardOverlay = document.getElementById('project-package-wizard-overlay');
  const projectPackageWizardBody = document.getElementById('project-package-wizard-body');
  const projectEntityEditorOverlay = document.getElementById('project-entity-editor-overlay');
  const projectEntityEditorTitle = document.getElementById('project-entity-editor-title');
  const projectEntityEditorSubtitle = document.getElementById('project-entity-editor-subtitle');
  const projectEntityEditorForm = document.getElementById('project-entity-editor-form');
  const projectEntityLabelsInput = document.getElementById('project-entity-labels');
  const projectEntityNoteInput = document.getElementById('project-entity-note');
  const projectEntitySubmitButton = document.getElementById('project-entity-submit');
  const projectNotesForm = document.getElementById('project-notes-form');
  const projectNotesInput = document.getElementById('project-notes-input');
  const projectNotesSaveStatus = document.getElementById('project-notes-save-status');
  const projectLabelsForm = document.getElementById('project-labels-form');
  const projectLabelsInput = document.getElementById('project-labels-input');
  const projectLabelsSaveButton = document.getElementById('project-labels-save-btn');
  const projectLabelsSaveStatus = document.getElementById('project-labels-save-status');
  const projectWorkspaceMessage = document.getElementById('project-workspace-message');
  const EntityMetadataClient = (
    typeof window !== 'undefined' && window.DarklabEntityMetadata
  ) || (
    typeof global !== 'undefined' && global.DarklabEntityMetadata
  ) || (
    typeof globalThis !== 'undefined' && globalThis.DarklabEntityMetadata
  ) || {};

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
  const PROJECT_TARGET_NOTES_MAX_LENGTH = 20000;
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
  let projectWorkspaceFilteredFindings = new Map();
  let projectWorkspaceLoading = false;
  let projectWorkspaceSelectedId = '';
  let projectWorkspaceTab = 'details';
  let projectWorkspaceFindingsLoadingId = '';
  let projectWorkspaceFindingsLoadingPromise = null;
  let projectWorkspaceFilteredFindingsLoadingKey = '';
  let projectWorkspaceEditingTargetId = '';
  let projectWorkspaceEditingEntity = null;
  let projectWorkspaceLastTargetType = 'domain';
  let projectWorkspaceTargetFilters = new Map();
  let projectWorkspaceRunFilters = new Map();
  let projectWorkspaceFindingStatusFilters = new Map();
  let projectWorkspaceFindingLabelFilters = new Map();
  let projectWorkspaceFindingNoteStateFilters = new Map();
  let projectWorkspaceCollapsedFindingGroups = new Set();
  let projectWorkspaceCollapsedArtifactGroups = new Set();
  let projectPackageWizard = null;
  let projectNotesSaveTimer = null;
  let projectNotesSaveSeq = 0;
  let projectNotesSavedDelayTimer = null;
  let projectNotesSavedHideTimer = null;
  let projectLabelsSavedHideTimer = null;
  let projectFilterSortDividerSyncScheduled = false;
  let projectFilterSortDividerSyncRoot = null;
  const PROJECT_NOTES_AUTOSAVE_DELAY_MS = 450;
  const FIELD_SAVED_INDICATOR_DELAY_MS = 200;
  const FIELD_SAVED_INDICATOR_VISIBLE_MS = 1600;
  const PROJECT_LABELS_SAVED_VISIBLE_MS = 2000;
  const PROJECT_WORKSPACE_BROADCAST_KEY = 'darklab_project_workspace_changed';
  const PROJECT_FINDING_SORT_OPTIONS = [
    { value: 'source', label: 'Source order' },
    { value: 'run', label: 'Run' },
    { value: 'severity', label: 'Severity' },
    { value: 'review', label: 'Review state' },
    { value: 'target', label: 'Target' },
    { value: 'newest', label: 'Newest run' },
  ];
  const PROJECT_FINDING_NOTE_STATE_OPTIONS = [
    { value: 'all', label: 'All notes' },
    { value: 'noted', label: 'With notes' },
    { value: 'unnoted', label: 'Without notes' },
  ];
  const PROJECT_FINDING_SEVERITY_RANK = {
    critical: 0,
    high: 1,
    medium: 2,
    low: 3,
    info: 4,
  };
  const PROJECT_FINDING_REVIEW_RANK = FINDING_REVIEW_STATES.reduce((acc, state, index) => {
    acc[state.value] = index;
    return acc;
  }, {});
  let projectWorkspaceExternalRefreshTimer = null;
  let projectWorkspaceFindingSort = new Map();

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

  function _bindProjectRuntimePressable(el, options = {}) {
    if (el && typeof bindPressable === 'function') {
      bindPressable(el, { onActivate: () => {}, refocusComposer: false, ...options });
    }
    return el;
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

  function _showProjectWorkspaceToast(text, tone = 'success') {
    const toastFn = typeof showToast === 'function'
      ? showToast
      : (global && typeof global.showToast === 'function' ? global.showToast : null);
    if (!toastFn) return false;
    toastFn(text, tone);
    return true;
  }

  function _setProjectWorkspaceMessage(text = '', { error = false } = {}) {
    if (!projectWorkspaceMessage) return;
    let messageText = projectWorkspaceMessage.querySelector('.project-workspace-message-text');
    if (!messageText) {
      projectWorkspaceMessage.replaceChildren();
      messageText = document.createElement('span');
      messageText.className = 'project-workspace-message-text';
      const dismiss = document.createElement('button');
      dismiss.type = 'button';
      dismiss.className = 'btn btn-ghost btn-compact project-workspace-message-dismiss';
      dismiss.dataset.projectMessageDismiss = '1';
      dismiss.setAttribute('aria-label', 'Dismiss project message');
      dismiss.textContent = '✕';
      projectWorkspaceMessage.append(messageText, dismiss);
    }
    if (text && !error && _showProjectWorkspaceToast(text)) {
      messageText.textContent = '';
      projectWorkspaceMessage.classList.add('u-hidden');
      projectWorkspaceMessage.classList.remove('is-error');
      return;
    }
    messageText.textContent = text;
    projectWorkspaceMessage.classList.toggle('u-hidden', !text);
    projectWorkspaceMessage.classList.toggle('is-error', !!error);
  }

  async function _projectResponseError(resp, fallback) {
    let message = fallback;
    try {
      const data = await resp.json();
      if (data && data.error) message = data.error;
    } catch (_) {}
    return new Error(message || fallback);
  }

  function _projectTargetDiscoveryMessage(count) {
    const total = Number(count || 0);
    if (total === 1) return '1 project target discovered.';
    return `${total.toLocaleString()} project targets discovered.`;
  }

  function _pulseProjectNavTargets() {
    const controls = [];
    railNav?.querySelectorAll('[data-action="projects"]').forEach(control => controls.push(control));
    if (mobileProjectRow) controls.push(mobileProjectRow);
    controls.forEach((control) => {
      control.classList.add('has-project-target-discovery');
      window.setTimeout(() => {
        control.classList.remove('has-project-target-discovery');
      }, 5000);
    });
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
      { id: 'notes', label: 'notes', value: counts.notes, tab: 'details' },
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

  function _projectFindingLabelFilterSet(projectId = projectWorkspaceSelectedId) {
    const normalized = String(projectId || '');
    if (!normalized) return new Set();
    if (!projectWorkspaceFindingLabelFilters.has(normalized)) {
      projectWorkspaceFindingLabelFilters.set(normalized, new Set());
    }
    return projectWorkspaceFindingLabelFilters.get(normalized);
  }

  function _projectFindingLabelOptions(projectId = projectWorkspaceSelectedId) {
    const labels = new Set();
    _projectFindingItems(projectId).forEach((finding) => {
      _entityLabelValues(finding).forEach(label => labels.add(label));
    });
    return [...labels].sort((left, right) => left.localeCompare(right, undefined, { sensitivity: 'base' }));
  }

  function _projectFindingLabelFilterValues(projectId = projectWorkspaceSelectedId) {
    const available = new Set(_projectFindingLabelOptions(projectId));
    const filters = _projectFindingLabelFilterSet(projectId);
    [...filters].forEach((label) => {
      if (!available.has(label)) filters.delete(label);
    });
    return [...filters];
  }

  function _projectFindingLabelFilterActive(projectId = projectWorkspaceSelectedId) {
    return _projectFindingLabelFilterValues(projectId).length > 0;
  }

  function _projectFindingNoteStateValue(projectId = projectWorkspaceSelectedId) {
    const value = String(projectWorkspaceFindingNoteStateFilters.get(String(projectId || '')) || 'all');
    return PROJECT_FINDING_NOTE_STATE_OPTIONS.some(option => option.value === value) ? value : 'all';
  }

  function _projectFindingNoteStateFilterActive(projectId = projectWorkspaceSelectedId) {
    return _projectFindingNoteStateValue(projectId) !== 'all';
  }

  function _projectFindingSortValue(projectId = projectWorkspaceSelectedId) {
    const value = String(projectWorkspaceFindingSort.get(String(projectId || '')) || 'source');
    return PROJECT_FINDING_SORT_OPTIONS.some(option => option.value === value) ? value : 'source';
  }

  function _projectFindingTargetText(summary, finding) {
    const targetIds = [..._projectFindingTargetIds(finding)];
    if (!targetIds.length) return '';
    return targetIds
      .map(targetId => _projectTargetLabel(summary, targetId))
      .filter(Boolean)
      .join(', ');
  }

  function _projectFindingRunStarted(summary, finding) {
    const run = _projectRunById(summary, finding && finding.run_id);
    const timestamp = Date.parse(String(run && run.started || finding && finding.created || ''));
    return Number.isFinite(timestamp) ? timestamp : 0;
  }

  function _compareProjectFindingText(left, right) {
    return String(left || '').localeCompare(String(right || ''), undefined, { sensitivity: 'base', numeric: true });
  }

  function _sortProjectFindings(findings, projectId, summary) {
    const sortValue = _projectFindingSortValue(projectId);
    if (sortValue === 'source') return findings;
    return findings.slice().sort((left, right) => {
      if (sortValue === 'severity') {
        const leftRank = PROJECT_FINDING_SEVERITY_RANK[String(left && left.severity || '').toLowerCase()] ?? 99;
        const rightRank = PROJECT_FINDING_SEVERITY_RANK[String(right && right.severity || '').toLowerCase()] ?? 99;
        if (leftRank !== rightRank) return leftRank - rightRank;
      } else if (sortValue === 'review') {
        const leftRank = PROJECT_FINDING_REVIEW_RANK[String(left && left.review_state || 'new')] ?? 99;
        const rightRank = PROJECT_FINDING_REVIEW_RANK[String(right && right.review_state || 'new')] ?? 99;
        if (leftRank !== rightRank) return leftRank - rightRank;
      } else if (sortValue === 'target') {
        const targetCompare = _compareProjectFindingText(
          _projectFindingTargetText(summary, left),
          _projectFindingTargetText(summary, right),
        );
        if (targetCompare) return targetCompare;
      } else if (sortValue === 'newest') {
        const timeCompare = _projectFindingRunStarted(summary, right) - _projectFindingRunStarted(summary, left);
        if (timeCompare) return timeCompare;
      }
      const runCompare = _compareProjectFindingText(
        left && (left.run_command || left.run_id),
        right && (right.run_command || right.run_id),
      );
      if (runCompare) return runCompare;
      const leftLine = Number(left && left.line_number);
      const rightLine = Number(right && right.line_number);
      if (Number.isFinite(leftLine) && Number.isFinite(rightLine) && leftLine !== rightLine) return leftLine - rightLine;
      return _compareProjectFindingText(left && (left.title || left.raw_line), right && (right.title || right.raw_line));
    });
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

  function _projectArtifactGroupKey(projectId, runId) {
    return `${String(projectId || '')}\x1f${String(runId || '')}`;
  }

  function _projectArtifactGroupCollapsed(projectId, runId) {
    return projectWorkspaceCollapsedArtifactGroups.has(_projectArtifactGroupKey(projectId, runId));
  }

  function _projectRunItems(summary) {
    return summary && Array.isArray(summary.runs) ? summary.runs : [];
  }

  function _projectRunById(summary, runId) {
    const normalized = String(runId || '');
    if (!normalized) return null;
    return _projectRunItems(summary).find(run => String(run.id || '') === normalized) || null;
  }

  function _projectComparableRuns(summary) {
    return _projectRunItems(summary).filter(run => run && run.id);
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
    const edit = document.createElement('button');
    edit.type = 'button';
    edit.className = 'btn btn-secondary btn-compact project-artifact-action';
    edit.dataset.projectAction = 'edit-artifact-metadata';
    edit.dataset.projectId = String(projectId || '');
    edit.dataset.artifactId = String(artifact.id || '');
    edit.textContent = 'Edit';
    _bindProjectRuntimePressable(edit);
    actions.appendChild(edit);
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
      _bindProjectRuntimePressable(btn);
      actions.appendChild(btn);
    });
    wrap.appendChild(actions);
    return wrap;
  }

  function _entityLabelValues(entity) {
    const labels = entity && Array.isArray(entity.labels) ? entity.labels : [];
    return labels
      .map(label => String(label && typeof label === 'object' ? label.label : label || '').trim())
      .filter(Boolean);
  }

  function _entityNoteBody(entity) {
    const note = entity && entity.note && typeof entity.note === 'object' ? entity.note : null;
    return note ? String(note.body || '').trim() : '';
  }

  function _entityMetadataChips(entity) {
    const chips = _entityLabelValues(entity).map(label => ({ label, kind: 'label' }));
    if (_entityNoteBody(entity)) chips.push({ label: 'note', kind: 'note' });
    return chips;
  }

  function _entityMetadataChipClass(kind = 'label') {
    const tone = String(kind || '') === 'note' ? 'badge-tone-cyan' : 'badge-tone-muted';
    return `project-explorer-metadata-chip badge ${tone}`;
  }

  function _projectLabelChips(project) {
    return _entityLabelValues(project).map(label => ({ label, kind: 'label' }));
  }

  function _appendProjectLabelChips(parent, project, { className = 'project-label-chips' } = {}) {
    const chips = _projectLabelChips(project);
    if (!parent || !chips.length) return;
    const wrap = document.createElement('div');
    wrap.className = className;
    for (const chip of chips) {
      const node = document.createElement('span');
      node.className = _entityMetadataChipClass(chip.kind);
      node.textContent = chip.label;
      wrap.appendChild(node);
    }
    parent.appendChild(wrap);
  }

  function _entityTitleForEditor(entityType, entity) {
    if (entityType === 'finding') {
      return String(entity && (entity.title || entity.raw_line || entity.id) || 'Finding');
    }
    if (entityType === 'run') {
      return String(entity && (entity.command || entity.id) || 'Run');
    }
    if (entityType === 'snapshot') {
      return String(entity && (entity.label || entity.id) || 'Snapshot');
    }
    if (entityType === 'package') {
      return String(entity && (entity.name || entity.id) || 'Package');
    }
    if (entityType === 'run_file_artifact') {
      return String(entity && (entity.display_name || entity.workspace_path || entity.id) || 'Artifact');
    }
    return String(entity && entity.id || 'Entity');
  }

  function _entityEditorLabelForType(entityType) {
    if (entityType === 'finding') return 'FINDING';
    if (entityType === 'run') return 'RUN';
    if (entityType === 'snapshot') return 'SNAPSHOT';
    if (entityType === 'run_file_artifact') return 'ARTIFACT';
    if (entityType === 'project') return 'PROJECT';
    if (entityType === 'package') return 'PACKAGE';
    if (entityType === 'workspace_file') return 'WORKSPACE FILE';
    if (entityType === 'target') return 'TARGET';
    return 'METADATA';
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

  function _projectPackageDownloadName(pkg) {
    const raw = String(pkg && pkg.name || 'evidence-package').trim().toLowerCase();
    const safe = raw.replace(/[^a-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '');
    return `${safe || 'evidence-package'}.zip`;
  }

  function _downloadBlobAsAttachment(blob, filename, successMessage = '') {
    downloadBlobAsAttachment(blob, filename);
    if (successMessage) _setProjectWorkspaceMessage(successMessage);
  }

  function _closeProjectPackageManifest() {
    if (!projectPackageManifestOverlay) return;
    projectPackageManifestOverlay.classList.add('u-hidden');
    projectPackageManifestOverlay.classList.remove('open');
    projectPackageManifestOverlay.setAttribute('aria-hidden', 'true');
    if (projectPackageManifestJson) projectPackageManifestJson.textContent = '';
  }

  function isProjectPackageManifestOpen() {
    return !!(projectPackageManifestOverlay && projectPackageManifestOverlay.classList.contains('open'));
  }

  function _openProjectPackageManifest(pkg) {
    if (!projectPackageManifestOverlay || !projectPackageManifestJson) {
      throw new Error('Manifest preview is not available.');
    }
    const name = String(pkg && pkg.name || 'package').trim() || 'package';
    if (projectPackageManifestTitle) projectPackageManifestTitle.textContent = `${name} manifest`;
    const manifest = pkg && pkg.manifest && typeof pkg.manifest === 'object' ? pkg.manifest : {};
    projectPackageManifestJson.textContent = JSON.stringify(manifest, null, 2);
    projectPackageManifestOverlay.classList.remove('u-hidden');
    projectPackageManifestOverlay.classList.add('open');
    projectPackageManifestOverlay.setAttribute('aria-hidden', 'false');
    window.setTimeout(() => {
      projectPackageManifestOverlay.querySelector('.project-package-manifest-close')?.focus();
    }, 0);
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
      { size: artifact.current_byte_size ?? artifact.byte_size ?? null, elevated: true },
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
    _downloadBlobAsAttachment(
      blob,
      _projectArtifactDownloadName(artifactPath, artifactId || 'artifact'),
      'Artifact download started.',
    );
  }

  function _projectPackageItems(summary) {
    return summary && Array.isArray(summary.packages) ? summary.packages : [];
  }

  function _projectPackagePresetDefaults(preset, summary, findings) {
    const normalizedPreset = String(preset || 'evidence').trim() || 'evidence';
    const runs = _projectRunItems(summary);
    const artifacts = _projectArtifactItems(summary);
    const targets = _projectTargetItems(summary);
    const findingItems = Array.isArray(findings) ? findings : [];
    const runIds = runs.map(run => String(run.id || '')).filter(Boolean);
    const findingRunIds = new Set(findingItems.map(finding => String(finding.run_id || '')).filter(Boolean));
    const redactionMode = normalizedPreset === 'redacted' ? 'redacted' : 'raw';
    const includeArtifacts = normalizedPreset !== 'summary' && redactionMode !== 'redacted';
    const selectedFindings = findingItems.filter(finding => (
      normalizedPreset === 'full' || String(finding.review_state || 'new') !== 'false_positive'
    ));
    const selectedTranscriptRunIds = normalizedPreset === 'summary'
      ? []
      : runIds.filter(runId => findingRunIds.has(runId));
    return {
      preset: normalizedPreset,
      step: 1,
      includeArtifacts,
      redactionMode,
      includePrivateNotes: false,
      name: '',
      description: '',
      labels: '',
      notes: '',
      collapsedRunIds: new Set(),
      selection: {
        runIds: new Set(runIds),
        transcriptRunIds: new Set(selectedTranscriptRunIds),
        findingIds: new Set(selectedFindings.map(finding => String(finding.id || '')).filter(Boolean)),
        artifactIds: new Set(includeArtifacts ? artifacts.map(artifact => String(artifact.id || '')).filter(Boolean) : []),
        targetIds: new Set(targets.map(target => String(target.id || '')).filter(Boolean)),
      },
    };
  }

  function _projectPackageWizardActive(projectId = projectWorkspaceSelectedId) {
    return !!(projectPackageWizard && String(projectPackageWizard.projectId || '') === String(projectId || ''));
  }

  function isProjectPackageWizardOpen() {
    return !!(projectPackageWizardOverlay && projectPackageWizardOverlay.classList.contains('open'));
  }

  function isProjectEntityEditorOpen() {
    return !!(projectEntityEditorOverlay && projectEntityEditorOverlay.classList.contains('open'));
  }

  function _closeProjectEntityEditor() {
    if (!projectEntityEditorOverlay) return;
    projectEntityEditorOverlay.classList.add('u-hidden');
    projectEntityEditorOverlay.classList.remove('open');
    projectEntityEditorOverlay.setAttribute('aria-hidden', 'true');
    projectWorkspaceEditingEntity = null;
    if (projectEntityEditorForm) {
      projectEntityEditorForm.dataset.projectId = '';
      projectEntityEditorForm.dataset.entityType = '';
      projectEntityEditorForm.dataset.entityId = '';
    }
  }

  function _openProjectEntityEditor(projectId, entityType, entity, options = {}) {
    if (!projectEntityEditorOverlay || !projectEntityEditorForm || !projectEntityLabelsInput || !projectEntityNoteInput) {
      throw new Error('Metadata editor is not available.');
    }
    const entityId = String(entity && entity.id || '');
    if (!entityType || !entityId) throw new Error('Entity is missing its identifier.');
    const title = _entityTitleForEditor(entityType, entity);
    projectWorkspaceEditingEntity = {
      projectId: String(projectId || ''),
      entityType: String(entityType),
      entityId,
      entity,
      onSaved: typeof options.onSaved === 'function' ? options.onSaved : null,
    };
    projectEntityEditorForm.dataset.projectId = String(projectId || '');
    projectEntityEditorForm.dataset.entityType = String(entityType);
    projectEntityEditorForm.dataset.entityId = entityId;
    if (projectEntityEditorTitle) {
      projectEntityEditorTitle.textContent = `EDIT ${_entityEditorLabelForType(entityType)}`;
    }
    if (projectEntityEditorSubtitle) projectEntityEditorSubtitle.textContent = title;
    projectEntityLabelsInput.value = _entityLabelValues(entity).join(', ');
    projectEntityNoteInput.value = _entityNoteBody(entity);
    if (projectEntitySubmitButton) projectEntitySubmitButton.textContent = 'Save';
    projectEntityEditorOverlay.classList.remove('u-hidden');
    projectEntityEditorOverlay.classList.add('open');
    projectEntityEditorOverlay.setAttribute('aria-hidden', 'false');
    window.setTimeout(() => projectEntityLabelsInput.focus(), 0);
  }

  global.openEntityMetadataEditor = function openEntityMetadataEditor(entityType, entity, options = {}) {
    const projectId = options && Object.prototype.hasOwnProperty.call(options, 'projectId')
      ? options.projectId
      : '';
    _openProjectEntityEditor(projectId, entityType, entity, options);
  };

  function _hideProjectPackageWizardOverlay() {
    if (!projectPackageWizardOverlay) return;
    projectPackageWizardOverlay.classList.add('u-hidden');
    projectPackageWizardOverlay.classList.remove('open');
    projectPackageWizardOverlay.setAttribute('aria-hidden', 'true');
    if (projectPackageWizardBody) projectPackageWizardBody.replaceChildren();
  }

  function _renderProjectPackageWizardModal({ focus = false, scrollTop = null } = {}) {
    if (!projectPackageWizard || !projectPackageWizardOverlay || !projectPackageWizardBody) {
      _hideProjectPackageWizardOverlay();
      return;
    }
    const projectId = String(projectPackageWizard.projectId || projectWorkspaceSelectedId || '');
    if (!projectId) {
      _hideProjectPackageWizardOverlay();
      return;
    }
    projectPackageWizardBody.replaceChildren();
    _renderProjectPackageWizard(projectPackageWizardBody, projectId, _projectSummary(projectId));
    projectPackageWizardOverlay.classList.remove('u-hidden');
    projectPackageWizardOverlay.classList.add('open');
    projectPackageWizardOverlay.setAttribute('aria-hidden', 'false');
    if (typeof global.enhanceAppSelects === 'function') {
      global.enhanceAppSelects(projectPackageWizardBody);
    }
    if (Number.isFinite(scrollTop)) {
      const scrollBody = projectPackageWizardBody.querySelector('.project-package-wizard-body');
      if (scrollBody) scrollBody.scrollTop = Number(scrollTop);
    }
    if (focus) {
      window.setTimeout(() => {
        projectPackageWizardBody.querySelector('[data-project-action="package-wizard-cancel"]')?.focus();
      }, 0);
    }
  }

  function _projectPackageSuggestedName(project, preset) {
    const slug = String(project && (project.slug || project.name) || 'project').trim().toLowerCase()
      .replace(/[^a-z0-9._-]+/g, '-')
      .replace(/^-+|-+$/g, '') || 'project';
    const today = new Date().toISOString().slice(0, 10);
    return `${slug}-${today}-${String(preset || 'evidence')}`;
  }

  function _openProjectPackageWizard(projectId, preset = 'evidence') {
    const summary = _projectSummary(projectId);
    const findings = _projectFindingItems(projectId);
    projectPackageWizard = {
      projectId: String(projectId || ''),
      ..._projectPackagePresetDefaults(preset, summary, findings),
    };
    projectPackageWizard.name = _projectPackageSuggestedName(_selectedProject(), projectPackageWizard.preset);
    _setProjectWorkspaceMessage('');
    if (!_projectFindingsLoaded(projectId)) {
      _loadProjectFindings(projectId).then(() => {
        if (_projectPackageWizardActive(projectId)) {
          const refreshed = _projectPackagePresetDefaults(projectPackageWizard.preset, _projectSummary(projectId), _projectFindingItems(projectId));
          refreshed.name = projectPackageWizard.name;
          refreshed.description = projectPackageWizard.description;
          refreshed.labels = projectPackageWizard.labels || '';
          refreshed.notes = projectPackageWizard.notes || '';
          refreshed.collapsedRunIds = projectPackageWizard.collapsedRunIds || new Set();
          projectPackageWizard = { projectId: String(projectId || ''), ...refreshed };
          _renderProjectExplorer();
          _renderProjectPackageWizardModal();
        }
      }).catch(() => {});
    }
    _renderProjectExplorer();
    _renderProjectPackageWizardModal({ focus: true });
  }

  function _projectPackageManifestIds(manifest, key, fallbackItems = []) {
    const selected = manifest && typeof manifest === 'object' ? manifest.selected_entity_ids : null;
    if (selected && typeof selected === 'object' && Array.isArray(selected[key])) {
      return new Set(selected[key].map(value => String(value || '')).filter(Boolean));
    }
    return new Set(fallbackItems.map(item => String(item && item.id || '')).filter(Boolean));
  }

  function _openProjectPackageWizardFromPackage(projectId, pkg) {
    const summary = _projectSummary(projectId);
    const manifest = pkg && typeof pkg.manifest === 'object' && pkg.manifest ? pkg.manifest : {};
    const preset = String(manifest.preset || pkg?.preset || 'custom') || 'custom';
    const redactionMode = String(pkg?.redaction_mode || manifest.redaction_mode || 'raw') === 'redacted'
      ? 'redacted'
      : 'raw';
    const options = manifest.options && typeof manifest.options === 'object' ? manifest.options : {};
    const includeArtifacts = redactionMode === 'redacted'
      ? false
      : Boolean(pkg?.include_artifacts ?? options.raw_artifacts);
    const selectedRunIds = _projectPackageManifestIds(manifest, 'run_ids', _projectRunItems(summary));
    projectPackageWizard = {
      projectId: String(projectId || ''),
      preset,
      step: 2,
      includeArtifacts,
      redactionMode,
      includePrivateNotes: !!manifest.include_private_notes,
      name: String(pkg?.name || _projectPackageSuggestedName(_selectedProject(), preset)),
      description: String(pkg?.description || ''),
      labels: _entityLabelValues(pkg).join(', '),
      notes: _entityNoteBody(pkg),
      collapsedRunIds: new Set(),
      selection: {
        runIds: selectedRunIds,
        transcriptRunIds: _projectPackageManifestIds(
          manifest,
          'transcript_run_ids',
          [...selectedRunIds].map(id => ({ id })),
        ),
        findingIds: _projectPackageManifestIds(manifest, 'finding_ids', _projectFindingItems(projectId)),
        artifactIds: _projectPackageManifestIds(manifest, 'artifact_ids', _projectArtifactItems(summary)),
        targetIds: _projectPackageManifestIds(manifest, 'target_ids', _projectTargetItems(summary)),
      },
    };
    _setProjectWorkspaceMessage('');
    if (!_projectFindingsLoaded(projectId)) {
      _loadProjectFindings(projectId).then(() => {
        if (_projectPackageWizardActive(projectId)) {
          _renderProjectExplorer();
          _renderProjectPackageWizardModal();
        }
      }).catch(() => {});
    }
    projectWorkspaceTab = 'packages';
    _renderProjectExplorer();
    _renderProjectPackageWizardModal({ focus: true });
  }

  function _closeProjectPackageWizard({ render = true } = {}) {
    projectPackageWizard = null;
    _hideProjectPackageWizardOverlay();
    _setProjectWorkspaceMessage('');
    if (render) _renderProjectExplorer();
  }

  function _projectPackageById(summary, packageId) {
    const normalized = String(packageId || '').trim();
    if (!normalized) return null;
    return _projectPackageItems(summary).find(item => String(item && item.id || '') === normalized) || null;
  }

  function _projectPackageAccessory(projectId, pkg) {
    const wrap = document.createElement('div');
    wrap.className = 'project-package-accessory';
    const actions = document.createElement('div');
    actions.className = 'project-package-actions';
    [
      ['package-edit', 'Edit'],
      ['package-download', 'Download'],
      ['package-repackage', 'Re-package'],
      ['package-manifest', 'View manifest'],
      ['package-delete', 'Delete'],
    ].forEach(([actionName, label]) => {
      const btn = _makeProjectButton(
        label,
        actionName,
        String(projectId || ''),
        'secondary',
        actionName === 'package-delete' ? 'danger' : '',
      );
      btn.classList.add('project-package-action');
      btn.dataset.packageId = String(pkg.id || '');
      actions.appendChild(btn);
    });
    wrap.appendChild(actions);
    return wrap;
  }

  function _setProjectPackageDownloadBusy(button, busy) {
    if (!button) return;
    if (busy) {
      button.dataset.originalText = button.textContent || 'Download';
      button.disabled = true;
      button.classList.add('is-preparing');
      button.setAttribute('aria-busy', 'true');
      button.textContent = 'Preparing...';
      return;
    }
    button.disabled = false;
    button.classList.remove('is-preparing');
    button.removeAttribute('aria-busy');
    button.textContent = button.dataset.originalText || 'Download';
    delete button.dataset.originalText;
  }

  function _projectPackageManifest(pkg) {
    return pkg && typeof pkg.manifest === 'object' && pkg.manifest ? pkg.manifest : {};
  }

  function _projectPackageCountsText(pkg) {
    const counts = _projectPackageManifest(pkg).counts || {};
    const parts = [
      ['run', counts.runs],
      ['finding', counts.findings],
      ['artifact', counts.artifacts],
      ['target', counts.targets],
    ].map(([label, value]) => {
      const count = Math.max(0, Number(value || 0));
      return `${count} ${label}${count === 1 ? '' : 's'}`;
    });
    return parts.join(' · ');
  }

  function _projectPackageMetaText(pkg) {
    const manifest = _projectPackageManifest(pkg);
    const parts = [];
    const preset = String(manifest.preset || 'custom').trim();
    const redaction = String(pkg?.redaction_mode || manifest.redaction_mode || 'raw').trim();
    if (preset) parts.push(preset);
    if (redaction) parts.push(redaction);
    const estimate = manifest.estimated_archive && typeof manifest.estimated_archive === 'object'
      ? Number(manifest.estimated_archive.estimated_uncompressed_bytes || 0)
      : 0;
    if (estimate > 0) parts.push(`~${_formatProjectBytes(estimate)}`);
    parts.push(pkg?.include_artifacts ? 'includes artifacts' : 'metadata only');
    return parts.join(' · ');
  }

  function _packageSelectionCheckbox({ kind, id, label, detail = '', checked = true, disabled = false, dataset = {} }) {
    const row = document.createElement('label');
    row.className = 'project-package-selection-row';
    if (disabled) row.classList.add('is-disabled');
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.checked = checked;
    input.disabled = disabled;
    input.dataset.projectPackageSelection = kind;
    input.value = String(id || '');
    Object.entries(dataset || {}).forEach(([key, value]) => {
      input.dataset[key] = String(value || '');
    });
    const text = document.createElement('span');
    text.className = 'project-package-selection-text';
    const labelEl = document.createElement('strong');
    labelEl.textContent = label;
    text.appendChild(labelEl);
    if (detail) {
      const detailEl = document.createElement('small');
      detailEl.textContent = detail;
      text.appendChild(detailEl);
    }
    row.append(input, text);
    return row;
  }

  function _packageWizardRunChildIds(runId, projectId, summary) {
    const normalizedRunId = String(runId || '');
    return {
      findingIds: _projectFindingItems(projectId)
        .filter(finding => String(finding && finding.run_id || '') === normalizedRunId)
        .map(finding => String(finding && finding.id || ''))
        .filter(Boolean),
      artifactIds: _projectArtifactItems(summary)
        .filter(artifact => String(artifact && artifact.run_id || '') === normalizedRunId)
        .map(artifact => String(artifact && artifact.id || ''))
        .filter(Boolean),
    };
  }

  function _appendPackageRunChildSelections(body, title, items, kind, runId, labelFn, detailFn) {
    if (!items.length) return;
    const selected = _packageWizardSetFor(kind);
    const group = document.createElement('div');
    group.className = 'project-package-run-child-group';
    const heading = document.createElement('h4');
    heading.textContent = `${title} (${items.length})`;
    group.appendChild(heading);
    items.forEach((item) => {
      const row = _packageSelectionCheckbox({
        kind,
        id: item.id,
        label: labelFn(item),
        detail: detailFn(item),
        checked: selected.has(String(item.id || '')),
        dataset: { runId },
      });
      row.classList.add('project-package-selection-row-nested');
      group.appendChild(row);
    });
    body.appendChild(group);
  }

  function _renderPackageRunSelections(section, projectId, summary) {
    const runs = _projectRunItems(summary);
    const selectedRuns = _packageWizardSetFor('run');
    const selectedTranscripts = _packageWizardSetFor('transcript');
    const findingsByRun = _groupBy(_projectFindingItems(projectId), finding => finding.run_id || '');
    const artifactsByRun = _groupBy(_projectArtifactItems(summary), artifact => artifact.run_id || '');
    runs.forEach((run) => {
      const runId = String(run.id || '');
      const runSelected = selectedRuns.has(runId);
      const collapsed = !!(projectPackageWizard?.collapsedRunIds?.has(runId));
      const group = document.createElement('div');
      group.className = 'project-package-run-selection';
      group.classList.toggle('is-collapsed', collapsed);
      const header = document.createElement('div');
      header.className = 'project-package-run-header';
      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'toggle-btn project-package-run-toggle';
      toggle.dataset.projectPackageRunToggle = '1';
      toggle.dataset.runId = runId;
      toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
      toggle.setAttribute('aria-label', `${collapsed ? 'Expand' : 'Collapse'} package options for this run`);
      toggle.textContent = '▾';
      _bindProjectRuntimePressable(toggle);
      const runRow = _packageSelectionCheckbox({
        kind: 'run',
        id: runId,
        label: run.command || run.id,
        detail: _formatProjectDate(run.started),
        checked: runSelected,
      });
      runRow.classList.add('project-package-selection-row-run');
      header.append(toggle, runRow);
      group.appendChild(header);
      const body = document.createElement('div');
      body.className = 'project-package-run-body';
      body.hidden = collapsed;
      const transcriptRow = _packageSelectionCheckbox({
        kind: 'transcript',
        id: runId,
        label: 'Include transcript',
        checked: runSelected && selectedTranscripts.has(runId),
        disabled: !runSelected,
        dataset: { runId },
      });
      transcriptRow.classList.add('project-package-selection-row-suboption');
      body.appendChild(transcriptRow);
      _appendPackageRunChildSelections(
        body,
        'Findings',
        findingsByRun.get(runId) || [],
        'finding',
        runId,
        item => item.title || item.raw_line || item.id,
        item => item.raw_line || '',
      );
      _appendPackageRunChildSelections(
        body,
        'Artifacts',
        artifactsByRun.get(runId) || [],
        'artifact',
        runId,
        item => item.display_name || item.workspace_path || item.id,
        item => _formatProjectBytes(item.byte_size),
      );
      group.appendChild(body);
      section.appendChild(group);
    });
  }

  function _projectPackageSelectionKind(kind, config) {
    return {
      ...config,
      missingIds: (projectId, summary) => {
        const current = new Set(config.currentItems(projectId, summary)
          .map(item => String(item && item.id || ''))
          .filter(Boolean));
        return Array.from(_packageWizardSetFor(kind)).filter(id => !current.has(String(id || '')));
      },
    };
  }

  const PROJECT_PACKAGE_SELECTION_KINDS = {
    run: _projectPackageSelectionKind('run', {
      set: wizard => wizard.selection.runIds,
      currentItems: (_projectId, summary) => _projectRunItems(summary),
      label: 'Run',
      missingReason: 'No longer linked to this project.',
    }),
    transcript: _projectPackageSelectionKind('transcript', {
      set: wizard => wizard.selection.transcriptRunIds,
      currentItems: (_projectId, summary) => _projectRunItems(summary),
      label: 'Transcript',
      missingReason: 'Source run is no longer linked to this project.',
    }),
    finding: _projectPackageSelectionKind('finding', {
      set: wizard => wizard.selection.findingIds,
      currentItems: projectId => _projectFindingItems(projectId),
      label: 'Finding',
      missingReason: 'No longer linked to this project.',
    }),
    artifact: _projectPackageSelectionKind('artifact', {
      set: wizard => wizard.selection.artifactIds,
      currentItems: (_projectId, summary) => _projectArtifactItems(summary),
      label: 'Artifact',
      missingReason: 'No longer linked to this project.',
    }),
    target: _projectPackageSelectionKind('target', {
      set: wizard => wizard.selection.targetIds,
      currentItems: (_projectId, summary) => _projectTargetItems(summary),
      label: 'Target',
      missingReason: 'No longer linked to this project.',
    }),
  };

  function _packageWizardKindConfig(kind) {
    return PROJECT_PACKAGE_SELECTION_KINDS[String(kind || '')] || null;
  }

  function _packageWizardSetFor(kind) {
    const config = _packageWizardKindConfig(kind);
    if (!projectPackageWizard || !config) return new Set();
    return config.set(projectPackageWizard) || new Set();
  }

  function _packageWizardMissingIds(kind, projectId, summary) {
    const config = _packageWizardKindConfig(kind);
    return config ? config.missingIds(projectId, summary) : [];
  }

  function _prunePackageWizardUnavailableSelections(items) {
    if (!projectPackageWizard || !Array.isArray(items)) return 0;
    let removed = 0;
    items.forEach((item) => {
      const kind = String(item && item.kind || '');
      const id = String(item && item.id || '');
      const selected = _packageWizardSetFor(kind);
      if (!id || !selected.has(id)) return;
      selected.delete(id);
      removed += 1;
    });
    return removed;
  }

  function _packageWizardSkippedPreview(projectId, summary) {
    const items = [];
    ['run', 'finding', 'target'].forEach((kind) => {
      const config = _packageWizardKindConfig(kind);
      _packageWizardMissingIds(kind, projectId, summary).forEach((id) => {
        items.push({
          kind,
          id,
          label: `${config.label} ${_shortProjectRunId(id) || id}`,
          reason: config.missingReason,
        });
      });
    });
    const transcriptConfig = _packageWizardKindConfig('transcript');
    _packageWizardMissingIds('transcript', projectId, summary).forEach((id) => {
      items.push({
        kind: 'transcript',
        id,
        label: `${transcriptConfig.label} ${_shortProjectRunId(id) || id}`,
        reason: transcriptConfig.missingReason,
      });
    });
    if (projectPackageWizard?.includeArtifacts) {
      _projectArtifactItems(summary)
        .filter(artifact => projectPackageWizard.selection.artifactIds.has(String(artifact.id || '')))
        .filter(artifact => _projectArtifactStatus(artifact) !== 'available')
        .forEach((artifact) => {
          items.push({
            kind: 'artifact',
            id: String(artifact.id || ''),
            label: artifact.display_name || artifact.workspace_path || artifact.id,
            reason: artifact.file_status_detail || 'Artifact is missing or changed and will be skipped.',
          });
        });
      _packageWizardMissingIds('artifact', projectId, summary).forEach((id) => {
        const config = _packageWizardKindConfig('artifact');
        items.push({
          kind: 'artifact',
          id,
          label: `${config.label} ${_shortProjectRunId(id) || id}`,
          reason: config.missingReason,
        });
      });
    }
    return items;
  }

  function _renderMissingPackageSelection(section, kind, projectId, summary) {
    _packageWizardMissingIds(kind, projectId, summary).forEach((id) => {
      section.appendChild(_packageSelectionCheckbox({
        kind,
        id,
        label: `Unavailable ${kind}`,
        detail: `${id} is no longer linked to this project. Uncheck it before creating the package.`,
        checked: true,
      }));
    });
  }

  function _renderPackageWizardStepHeader(wrap) {
    const steps = ['Preset', 'Include', 'Metadata', 'Preview'];
    const list = document.createElement('div');
    list.className = 'project-package-stepper';
    steps.forEach((label, index) => {
      const item = document.createElement('span');
      item.className = 'project-package-step' + (projectPackageWizard.step === index + 1 ? ' is-active' : '');
      item.textContent = `${index + 1}. ${label}`;
      list.appendChild(item);
    });
    wrap.appendChild(list);
  }

  function _renderPackageWizardPreset(wrap, projectId, summary) {
    const presets = [
      ['summary', 'Summary', 'Manifest only, no raw artifacts.'],
      ['evidence', 'Evidence', 'Findings, targets, runs, and selected artifacts.'],
      ['redacted', 'Redacted Evidence', 'Findings, targets, and transcripts with share redaction applied.'],
      ['full', 'Full archive', 'Everything currently linked to the project.'],
      ['custom', 'Custom', 'Start from the evidence preset and tune selections.'],
    ];
    const list = document.createElement('div');
    list.className = 'project-package-preset-list';
    presets.forEach(([id, title, detail]) => {
      const row = document.createElement('label');
      row.className = 'project-package-preset';
      row.classList.toggle('is-active', projectPackageWizard.preset === id);
      const input = document.createElement('input');
      input.type = 'radio';
      input.name = `project-package-preset-${projectId}`;
      input.value = id;
      input.checked = projectPackageWizard.preset === id;
      input.dataset.projectPackagePreset = '1';
      input.dataset.projectId = projectId;
      const text = document.createElement('span');
      text.className = 'project-package-preset-text';
      const titleEl = document.createElement('span');
      titleEl.textContent = title;
      const detailEl = document.createElement('small');
      detailEl.textContent = detail;
      text.append(titleEl, detailEl);
      row.append(input, text);
      list.appendChild(row);
    });
    wrap.appendChild(list);
    const metadata = document.createElement('div');
    metadata.className = 'project-package-preset-metadata';
    const labelsLabel = document.createElement('label');
    labelsLabel.textContent = 'Labels';
    const labelsInput = document.createElement('input');
    labelsInput.className = 'form-control form-control-compact';
    labelsInput.dataset.projectPackageField = 'labels';
    labelsInput.value = projectPackageWizard.labels || '';
    labelsInput.placeholder = 'handoff, retest';
    labelsInput.autocomplete = 'off';
    labelsLabel.appendChild(labelsInput);
    const notesLabel = document.createElement('label');
    notesLabel.textContent = 'Notes';
    const notesInput = document.createElement('textarea');
    notesInput.className = 'form-control form-control-compact';
    notesInput.dataset.projectPackageField = 'notes';
    notesInput.rows = 3;
    notesInput.value = projectPackageWizard.notes || '';
    notesInput.placeholder = 'Private package notes';
    notesLabel.appendChild(notesInput);
    metadata.append(labelsLabel, notesLabel);
    wrap.appendChild(metadata);
    const note = document.createElement('p');
    note.className = 'project-package-wizard-note';
    note.textContent = `${_projectRunItems(summary).length} runs, ${_projectFindingItems(projectId).length} findings, `
      + `${_projectArtifactItems(summary).length} artifacts, and ${_projectTargetItems(summary).length} targets are available.`;
    wrap.appendChild(note);
  }

  function _renderPackageWizardSelections(wrap, projectId, summary) {
    if (!_projectFindingsLoaded(projectId)) {
      wrap.appendChild(_emptyProjectPanel('Loading findings for package selection...'));
      return;
    }
    const sections = [
      ['Targets', 'target', _projectTargetItems(summary), item => _projectTargetFilterLabel(item), item => _entityNoteBody(item)],
    ];
    const runSection = document.createElement('section');
    runSection.className = 'project-package-selection-section';
    const runHeading = document.createElement('h3');
    const runCount = _projectRunItems(summary).length;
    runHeading.textContent = `Runs (${runCount})`;
    runSection.appendChild(runHeading);
    const runMissingIds = _packageWizardMissingIds('run', projectId, summary);
    const transcriptMissingIds = _packageWizardMissingIds('transcript', projectId, summary);
    const findingMissingIds = _packageWizardMissingIds('finding', projectId, summary);
    const artifactMissingIds = _packageWizardMissingIds('artifact', projectId, summary);
    if (!runCount && !runMissingIds.length && !transcriptMissingIds.length && !findingMissingIds.length && !artifactMissingIds.length) {
      runSection.appendChild(_emptyProjectPanel('No runs available.'));
    } else {
      _renderPackageRunSelections(runSection, projectId, summary);
      _renderMissingPackageSelection(runSection, 'run', projectId, summary);
      _renderMissingPackageSelection(runSection, 'transcript', projectId, summary);
      _renderMissingPackageSelection(runSection, 'finding', projectId, summary);
      _renderMissingPackageSelection(runSection, 'artifact', projectId, summary);
    }
    wrap.appendChild(runSection);
    sections.forEach(([title, kind, items, labelFn, detailFn]) => {
      const section = document.createElement('section');
      section.className = 'project-package-selection-section';
      const heading = document.createElement('h3');
      heading.textContent = `${title} (${items.length})`;
      section.appendChild(heading);
      const missingIds = _packageWizardMissingIds(kind, projectId, summary);
      if (!items.length && !missingIds.length) {
        section.appendChild(_emptyProjectPanel(`No ${title.toLowerCase()} available.`));
      } else {
        const selected = _packageWizardSetFor(kind);
        items.forEach((item) => {
          section.appendChild(_packageSelectionCheckbox({
            kind,
            id: item.id,
            label: labelFn(item),
            detail: detailFn(item),
            checked: selected.has(String(item.id || '')),
          }));
        });
        _renderMissingPackageSelection(section, kind, projectId, summary);
      }
      wrap.appendChild(section);
    });
    const privateLabel = document.createElement('label');
    privateLabel.className = 'project-package-selection-row';
    const privateInput = document.createElement('input');
    privateInput.type = 'checkbox';
    privateInput.checked = !!projectPackageWizard.includePrivateNotes;
    privateInput.dataset.projectPackagePrivateNotes = '1';
    const privateText = document.createElement('span');
    privateText.className = 'project-package-selection-text';
    const strong = document.createElement('strong');
    strong.textContent = 'Include private notes';
    const small = document.createElement('small');
    small.textContent = 'Private metadata stays excluded unless this is checked.';
    privateText.append(strong, small);
    privateLabel.append(privateInput, privateText);
    wrap.appendChild(privateLabel);
  }

  function _renderPackageWizardMetadata(wrap) {
    const form = document.createElement('div');
    form.className = 'project-package-metadata-form';
    const nameLabel = document.createElement('label');
    nameLabel.textContent = 'Name';
    const nameInput = document.createElement('input');
    nameInput.className = 'form-control form-control-compact';
    nameInput.dataset.projectPackageField = 'name';
    nameInput.value = projectPackageWizard.name;
    nameLabel.appendChild(nameInput);
    const descLabel = document.createElement('label');
    descLabel.textContent = 'Description';
    const descInput = document.createElement('textarea');
    descInput.className = 'form-control form-control-compact';
    descInput.dataset.projectPackageField = 'description';
    descInput.rows = 3;
    descInput.value = projectPackageWizard.description;
    descLabel.appendChild(descInput);
    const artifactsLabel = document.createElement('label');
    artifactsLabel.className = 'project-package-selection-row';
    const artifactsInput = document.createElement('input');
    artifactsInput.type = 'checkbox';
    artifactsInput.checked = !!projectPackageWizard.includeArtifacts;
    artifactsInput.disabled = projectPackageWizard.redactionMode === 'redacted';
    artifactsInput.dataset.projectPackageIncludeArtifacts = '1';
    const artifactsText = document.createElement('span');
    artifactsText.className = 'project-package-selection-text';
    const artifactsStrong = document.createElement('strong');
    artifactsStrong.textContent = 'Include selected raw artifacts';
    const artifactsSmall = document.createElement('small');
    artifactsSmall.textContent = projectPackageWizard.redactionMode === 'redacted'
      ? 'Redacted packages exclude raw artifacts because file contents are not sanitized yet.'
      : 'Static HTML, Markdown, and selected raw artifacts are included in the archive.';
    artifactsText.append(artifactsStrong, artifactsSmall);
    artifactsLabel.append(artifactsInput, artifactsText);
    const redactionLabel = document.createElement('label');
    redactionLabel.textContent = 'Redaction';
    const redactionSelect = document.createElement('select');
    redactionSelect.className = 'form-select';
    redactionSelect.dataset.projectPackageField = 'redaction_mode';
    [
      ['raw', 'Raw package'],
      ['redacted', 'Redacted package'],
    ].forEach(([value, label]) => {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = label;
      option.selected = projectPackageWizard.redactionMode === value;
      redactionSelect.appendChild(option);
    });
    redactionLabel.appendChild(redactionSelect);
    form.append(nameLabel, descLabel, redactionLabel, artifactsLabel);
    wrap.appendChild(form);
  }

  function _packageWizardManifestPreview(projectId, summary) {
    const estimate = _packageWizardEstimate(summary);
    const skippedPreview = _packageWizardSkippedPreview(projectId, summary);
    const projectPreview = {
      id: projectId,
      name: summary?.project?.name || '',
    };
    if (projectPackageWizard.includePrivateNotes && summary?.project?.note) {
      projectPreview.note = summary.project.note;
    }
    return {
      package_format_version: 1,
      preset: projectPackageWizard.preset,
      options: {
        manifest_json: true,
        raw_artifacts: !!projectPackageWizard.includeArtifacts,
        index_html: true,
        transcripts_html: projectPackageWizard.selection.transcriptRunIds.size > 0,
      },
      redaction_mode: projectPackageWizard.redactionMode || 'raw',
      include_private_notes: !!projectPackageWizard.includePrivateNotes,
      counts: {
        runs: projectPackageWizard.selection.runIds.size,
        findings: projectPackageWizard.selection.findingIds.size,
        artifacts: projectPackageWizard.selection.artifactIds.size,
        targets: projectPackageWizard.selection.targetIds.size,
      },
      selected_entity_ids: {
        run_ids: Array.from(projectPackageWizard.selection.runIds),
        transcript_run_ids: Array.from(projectPackageWizard.selection.transcriptRunIds)
          .filter(runId => projectPackageWizard.selection.runIds.has(String(runId || ''))),
        finding_ids: Array.from(projectPackageWizard.selection.findingIds),
        artifact_ids: Array.from(projectPackageWizard.selection.artifactIds),
        target_ids: Array.from(projectPackageWizard.selection.targetIds),
      },
      estimated_archive: estimate,
      skipped_preview: skippedPreview,
      project: projectPreview,
    };
  }

  function _packageWizardEstimate(summary) {
    const selectedRuns = _projectRunItems(summary)
      .filter(run => projectPackageWizard.selection.runIds.has(String(run.id || '')));
    const selectedTranscriptRuns = selectedRuns
      .filter(run => projectPackageWizard.selection.transcriptRunIds.has(String(run.id || '')));
    const selectedArtifacts = _projectArtifactItems(summary)
      .filter(artifact => projectPackageWizard.selection.artifactIds.has(String(artifact.id || '')));
    const selectedFindings = _projectFindingItems(projectPackageWizard.projectId)
      .filter(finding => projectPackageWizard.selection.findingIds.has(String(finding.id || '')));
    const selectedTargets = _projectTargetItems(summary)
      .filter(target => projectPackageWizard.selection.targetIds.has(String(target.id || '')));
    const rawArtifactBytes = projectPackageWizard.includeArtifacts
      ? selectedArtifacts
        .filter(artifact => _projectArtifactStatus(artifact) === 'available')
        .reduce((total, artifact) => total + Math.max(0, Number(artifact.byte_size || 0)), 0)
      : 0;
    const skippedArtifactCountEstimate = projectPackageWizard.includeArtifacts
      ? selectedArtifacts.filter(artifact => _projectArtifactStatus(artifact) !== 'available').length
      : 0;
    const transcriptHtmlBytes = selectedTranscriptRuns.reduce((total, run) => (
      total + 4096 + Math.max(0, Number(run.output_line_count || 0)) * 120
    ), 0);
    const metadataBytes = Math.max(
      16 * 1024,
      JSON.stringify({
        runs: selectedRuns.length,
        findings: selectedFindings.length,
        artifacts: selectedArtifacts.length,
        targets: selectedTargets.length,
      }).length + 16 * 1024,
    );
    const estimatedUncompressedBytes = rawArtifactBytes + transcriptHtmlBytes + metadataBytes;
    return {
      estimated_uncompressed_bytes: estimatedUncompressedBytes,
      estimated_archive_bytes: estimatedUncompressedBytes,
      raw_artifact_bytes: rawArtifactBytes,
      transcript_html_bytes: transcriptHtmlBytes,
      metadata_bytes: metadataBytes,
      selected_run_count: selectedRuns.length,
      selected_transcript_count: selectedTranscriptRuns.length,
      selected_artifact_count: selectedArtifacts.length,
      skipped_artifact_count_estimate: skippedArtifactCountEstimate,
      note: 'Pre-build estimate before ZIP compression; final download enforces archive caps and drift checks.',
    };
  }

  function _renderPackageWizardPreview(wrap, projectId, summary) {
    const preview = _packageWizardManifestPreview(projectId, summary);
    const estimate = preview.estimated_archive || {};
    const note = document.createElement('p');
    note.className = 'project-package-wizard-note';
    note.textContent = `Estimated package size before compression: ${_formatProjectBytes(estimate.estimated_uncompressed_bytes || 0)}.`;
    wrap.appendChild(note);
    if (Number(estimate.skipped_artifact_count_estimate || 0) > 0) {
      const skipped = document.createElement('p');
      skipped.className = 'project-package-wizard-note';
      skipped.textContent = `${estimate.skipped_artifact_count_estimate} selected artifact(s) are currently unavailable or changed and may be skipped.`;
      wrap.appendChild(skipped);
    }
    if (Array.isArray(preview.skipped_preview) && preview.skipped_preview.length) {
      const skippedWrap = document.createElement('div');
      skippedWrap.className = 'project-package-preview-skipped';
      const heading = document.createElement('h3');
      heading.textContent = 'Items needing attention';
      skippedWrap.appendChild(heading);
      const list = document.createElement('ul');
      preview.skipped_preview.forEach((item) => {
        const row = document.createElement('li');
        row.textContent = `${item.label || item.id}: ${item.reason || 'May be skipped.'}`;
        list.appendChild(row);
      });
      skippedWrap.appendChild(list);
      wrap.appendChild(skippedWrap);
    }
    const pre = document.createElement('pre');
    pre.className = 'project-package-manifest-json project-package-preview-json nice-scroll';
    pre.textContent = JSON.stringify(preview, null, 2);
    wrap.appendChild(pre);
  }

  function _renderProjectPackageWizard(container, projectId, summary) {
    const wizard = document.createElement('section');
    wizard.className = 'project-package-wizard';
    const header = document.createElement('div');
    header.className = 'project-package-wizard-header';
    const title = document.createElement('h2');
    title.id = 'project-package-wizard-title';
    title.textContent = 'New evidence package';
    const cancel = _makeProjectButton('Cancel', 'package-wizard-cancel', projectId);
    header.append(title, cancel);
    wizard.appendChild(header);
    _renderPackageWizardStepHeader(wizard);
    if (projectPackageWizard.notice) {
      const message = document.createElement('p');
      message.className = 'project-workspace-message project-package-wizard-message'
        + (projectPackageWizard.noticeError ? ' is-error' : '');
      message.textContent = projectPackageWizard.notice;
      wizard.appendChild(message);
    }
    const body = document.createElement('div');
    body.className = 'project-package-wizard-body nice-scroll';
    if (projectPackageWizard.step === 1) _renderPackageWizardPreset(body, projectId, summary);
    else if (projectPackageWizard.step === 2) _renderPackageWizardSelections(body, projectId, summary);
    else if (projectPackageWizard.step === 3) _renderPackageWizardMetadata(body);
    else _renderPackageWizardPreview(body, projectId, summary);
    wizard.appendChild(body);
    const footer = document.createElement('div');
    footer.className = 'project-package-wizard-footer';
    if (projectPackageWizard.step > 1) footer.appendChild(_makeProjectButton('Back', 'package-wizard-back', projectId));
    const next = _makeProjectButton(projectPackageWizard.step === 4 ? 'Create package' : 'Next', 'package-wizard-next', projectId);
    footer.appendChild(next);
    wizard.appendChild(footer);
    container.appendChild(wizard);
  }

  function _projectPackageWizardPayload() {
    return {
      name: String(projectPackageWizard.name || '').trim(),
      description: String(projectPackageWizard.description || '').trim(),
      preset: String(projectPackageWizard.preset || 'custom'),
      redaction_mode: String(projectPackageWizard.redactionMode || 'raw'),
      include_artifacts: !!projectPackageWizard.includeArtifacts,
      include_private_notes: !!projectPackageWizard.includePrivateNotes,
      labels: EntityMetadataClient.parseLabelInput(projectPackageWizard.labels || ''),
      notes: String(projectPackageWizard.notes || '').trim(),
      options: {
        manifest_json: true,
        index_html: true,
        transcripts_html: projectPackageWizard.selection.transcriptRunIds.size > 0,
      },
      selection: {
        run_ids: Array.from(projectPackageWizard.selection.runIds),
        transcript_run_ids: Array.from(projectPackageWizard.selection.transcriptRunIds)
          .filter(runId => projectPackageWizard.selection.runIds.has(String(runId || ''))),
        finding_ids: Array.from(projectPackageWizard.selection.findingIds),
        artifact_ids: Array.from(projectPackageWizard.selection.artifactIds),
        target_ids: Array.from(projectPackageWizard.selection.targetIds),
      },
    };
  }

  async function _createProjectPackageFromWizard(projectId) {
    if (!projectPackageWizard) return;
    const payload = _projectPackageWizardPayload();
    if (!payload.name) {
      _setProjectWorkspaceMessage('Package name is required.', { error: true });
      projectPackageWizard.notice = 'Package name is required.';
      projectPackageWizard.noticeError = true;
      projectPackageWizard.step = 3;
      _renderProjectPackageWizardModal();
      return;
    }
    const summary = _projectSummary(projectId);
    const missingSelections = _packageWizardSkippedPreview(projectId, summary)
      .filter(item => item.kind !== 'artifact' || String(item.reason || '').includes('No longer linked'));
    if (missingSelections.length) {
      const removedCount = _prunePackageWizardUnavailableSelections(missingSelections);
      const noun = removedCount === 1 ? 'item' : 'items';
      _setProjectWorkspaceMessage(`${removedCount} unavailable ${noun} removed; review your selection before continuing.`);
      projectPackageWizard.notice = `${removedCount} unavailable ${noun} removed; review your selection before continuing.`;
      projectPackageWizard.noticeError = false;
      projectPackageWizard.step = 2;
      _renderProjectPackageWizardModal();
      return;
    }
    await _projectWorkspaceRequest(`/projects/${encodeURIComponent(projectId)}/packages`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    projectPackageWizard = null;
    _hideProjectPackageWizardOverlay();
    await refreshProjectWorkspace();
    projectWorkspaceTab = 'packages';
    _setProjectWorkspaceMessage('Package created.');
  }

  async function _downloadProjectPackage(projectId, pkg) {
    const packageId = String(pkg && pkg.id || '').trim();
    const resp = await apiFetch(
      `/projects/${encodeURIComponent(projectId)}/packages/${encodeURIComponent(packageId)}/download`,
      { cache: 'no-store' },
    );
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.error || 'Unable to download package.');
    }
    const blob = await resp.blob();
    _downloadBlobAsAttachment(blob, _projectPackageDownloadName(pkg), 'Package download started.');
  }

  function _projectFindingItems(projectId = projectWorkspaceSelectedId) {
    return projectWorkspaceFindings.get(String(projectId || '')) || [];
  }

  function _projectFindingsLoaded(projectId = projectWorkspaceSelectedId) {
    return projectWorkspaceFindings.has(String(projectId || ''));
  }

  function _projectFindingServerFilterParams(projectId, summary = _projectSummary(projectId)) {
    const params = new URLSearchParams();
    _projectTargetFilterIds(projectId, summary).forEach(targetId => params.append('target_id', targetId));
    _projectRunFilterIds(projectId, summary).forEach(runId => params.append('run_id', runId));
    _projectFindingStatusFilterValues(projectId).forEach(status => params.append('review_state', status));
    _projectFindingLabelFilterValues(projectId).forEach(label => params.append('label', label));
    const noteState = _projectFindingNoteStateValue(projectId);
    if (noteState !== 'all') params.set('note_state', noteState);
    return params;
  }

  function _projectFindingServerFiltersActive(projectId = projectWorkspaceSelectedId, summary = _projectSummary(projectId)) {
    return _projectFindingServerFilterParams(projectId, summary).toString() !== '';
  }

  function _projectFindingFilteredKey(projectId = projectWorkspaceSelectedId, summary = _projectSummary(projectId)) {
    const normalized = String(projectId || '');
    const query = _projectFindingServerFilterParams(normalized, summary).toString();
    return query ? `${normalized}::${query}` : '';
  }

  function _projectFilteredFindingItems(projectId = projectWorkspaceSelectedId, summary = _projectSummary(projectId)) {
    const key = _projectFindingFilteredKey(projectId, summary);
    return key && projectWorkspaceFilteredFindings.has(key)
      ? projectWorkspaceFilteredFindings.get(key)
      : _projectFindingItems(projectId);
  }

  function _invalidateProjectFilteredFindings(projectId = '') {
    const normalized = String(projectId || '');
    if (!normalized) {
      projectWorkspaceFilteredFindings = new Map();
      projectWorkspaceFilteredFindingsLoadingKey = '';
      return;
    }
    const prefix = `${normalized}::`;
    [...projectWorkspaceFilteredFindings.keys()].forEach((key) => {
      if (String(key).startsWith(prefix)) projectWorkspaceFilteredFindings.delete(key);
    });
    if (projectWorkspaceFilteredFindingsLoadingKey.startsWith(prefix)) {
      projectWorkspaceFilteredFindingsLoadingKey = '';
    }
  }

  function _invalidateProjectFindings(projectId = '') {
    const normalized = String(projectId || '');
    if (normalized) {
      projectWorkspaceFindings.delete(normalized);
      _invalidateProjectFilteredFindings(normalized);
    } else {
      projectWorkspaceFindings = new Map();
      _invalidateProjectFilteredFindings();
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
    row.className = 'project-explorer-meta-row panel-row';
    const key = document.createElement('span');
    key.textContent = label;
    const val = document.createElement('span');
    val.textContent = String(value || '—');
    row.append(key, val);
    return row;
  }

  function _projectItemRow({ title, meta = '', detail = '', badge = '', chips = [], action = null, accessory = null }) {
    const row = document.createElement(action && !accessory ? 'button' : 'article');
    row.className = 'project-explorer-item panel-row' + (action && !accessory ? ' panel-row-clickable' : '');
    let contentHost = row;
    if (action) {
      if (row.tagName === 'BUTTON') {
        row.type = 'button';
        row.classList.add('control-row');
      }
      else if (accessory) {
        contentHost = document.createElement('button');
        contentHost.type = 'button';
        contentHost.className = 'control-row project-explorer-item-click-target';
      }
      contentHost.dataset.projectAction = action.action;
      Object.entries(action.dataset || {}).forEach(([key, value]) => {
        contentHost.dataset[key] = value;
      });
      _bindProjectRuntimePressable(contentHost);
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
    if (Array.isArray(chips) && chips.length) {
      const chipWrap = document.createElement('div');
      chipWrap.className = 'project-explorer-item-chips';
      chips.forEach((chip) => {
        const chipEl = document.createElement('span');
        chipEl.className = _entityMetadataChipClass(chip.kind);
        chipEl.textContent = String(chip.label || '');
        chipWrap.appendChild(chipEl);
      });
      main.appendChild(chipWrap);
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

  function _findingRowAccessory(finding, projectId) {
    const wrap = document.createElement('div');
    wrap.className = 'project-finding-row-actions';
    if (finding && finding.id) {
      const edit = _makeProjectButton('Edit', 'edit-finding-metadata', projectId);
      edit.dataset.findingId = String(finding.id || '');
      wrap.appendChild(edit);
      wrap.appendChild(_findingReviewControl(finding, projectId));
    }
    return wrap;
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

  function _setProjectTargetValueError(message = '', { target = 'value' } = {}) {
    const hasError = !!message;
    if (projectTargetValueInput) {
      projectTargetValueInput.setAttribute('aria-invalid', hasError && target === 'value' ? 'true' : 'false');
    }
    if (projectTargetNotesInput) {
      projectTargetNotesInput.setAttribute('aria-invalid', hasError && target === 'notes' ? 'true' : 'false');
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

  function _projectTargetNotesValidationError(notes) {
    const length = String(notes || '').trim().length;
    if (length <= PROJECT_TARGET_NOTES_MAX_LENGTH) return '';
    return `Target notes must be ${PROJECT_TARGET_NOTES_MAX_LENGTH.toLocaleString()} characters or fewer.`;
  }

  function _projectTargetEditorPayload() {
    return {
      type: String(projectTargetTypeSelect?.value || 'domain').trim() || 'domain',
      value: String(projectTargetValueInput?.value || '').trim(),
    };
  }

  function _projectTargetEditorMetadata() {
    return {
      labels: EntityMetadataClient.parseLabelInput(projectTargetLabelInput?.value || ''),
      noteBody: String(projectTargetNotesInput?.value || '').trim(),
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
    if (projectTargetLabelInput) projectTargetLabelInput.value = isEdit ? _entityLabelValues(target).join(', ') : '';
    if (projectTargetNotesInput) {
      projectTargetNotesInput.value = isEdit ? _entityNoteBody(target) : '';
      projectTargetNotesInput.setAttribute('aria-invalid', 'false');
    }
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
    if (String(target.review_state || '') === 'pending') {
      const badge = document.createElement('span');
      badge.className = 'project-target-auto-badge';
      badge.textContent = 'auto';
      badge.title = 'Discovered from command input';
      heading.appendChild(badge);
    }
    main.appendChild(heading);

    const chips = _entityMetadataChips(target);
    if (chips.length) {
      const chipWrap = document.createElement('div');
      chipWrap.className = 'project-explorer-item-chips project-target-metadata-chips';
      chips.forEach((chip) => {
        const chipEl = document.createElement('span');
        chipEl.className = _entityMetadataChipClass(chip.kind);
        chipEl.textContent = String(chip.label || '');
        chipWrap.appendChild(chipEl);
      });
      main.appendChild(chipWrap);
    }

    const actions = document.createElement('div');
    actions.className = 'project-target-actions';
    const edit = _makeProjectButton('Edit', 'edit-target', projectId);
    const remove = _makeProjectButton('Remove', 'delete-target', projectId);
    const targetId = String(target.id || '');
    const buttons = [];
    if (String(target.review_state || '') === 'pending') {
      buttons.push(_makeProjectButton('Confirm', 'confirm-target', projectId, 'secondary'));
      buttons.push(_makeProjectButton('Dismiss', 'dismiss-target', projectId));
    }
    buttons.push(edit, remove);
    buttons.forEach((btn) => {
      btn.dataset.targetId = targetId;
      btn.dataset.targetValue = String(target.value || '');
    });
    actions.append(...buttons);
    row.append(main, actions);
    return row;
  }

  function _projectRunRemoveControl(projectId, run) {
    const btn = _makeProjectButton('Remove', 'unlink-run', projectId);
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
    const counts = document.createElement('div');
    counts.className = 'project-run-row-counts';
    [
      ['finding', _projectRunFindingCount(projectId, runId), 'filter-run-findings'],
      ['artifact', _projectRunArtifactCount(summary, runId), 'filter-run-artifacts'],
    ].forEach(([label, count, action]) => {
      const chip = _makeProjectButton(`${count} ${label}${count === 1 ? '' : 's'}`, action, projectId, count ? 'secondary' : 'ghost');
      chip.classList.add('project-run-count-chip');
      chip.disabled = !count;
      chip.dataset.runId = runId;
      chip.dataset.runCommand = String(run.command || '');
      counts.appendChild(chip);
    });
    const actions = document.createElement('div');
    actions.className = 'project-run-row-buttons';
    const edit = _makeProjectButton('Edit', 'edit-run-metadata', projectId);
    edit.dataset.runId = runId;
    edit.dataset.runCommand = String(run.command || '');
    const restore = _makeProjectButton('Restore', 'open-run', projectId);
    restore.dataset.runId = runId;
    restore.dataset.runCommand = String(run.command || '');
    actions.appendChild(edit);
    actions.appendChild(restore);
    actions.appendChild(_projectRunRemoveControl(projectId, run));
    wrap.append(counts, actions);
    return wrap;
  }

  function _projectRunBaselineLabelOptions(runs) {
    const labels = new Set();
    (Array.isArray(runs) ? runs : []).forEach((run) => {
      _entityLabelValues(run).forEach(label => labels.add(label));
    });
    return [...labels].sort((left, right) => {
      if (left === 'baseline') return -1;
      if (right === 'baseline') return 1;
      return left.localeCompare(right, undefined, { sensitivity: 'base' });
    });
  }

  function _projectRunCompareOptionText(run) {
    const command = String(run && (run.command || run.id) || 'run');
    const labels = _entityLabelValues(run);
    return labels.length ? `${command} · ${labels.join(', ')}` : command;
  }

  function _projectRunCompareDatasetOptions(container, key) {
    try {
      const parsed = JSON.parse(String(container?.dataset?.[key] || '[]'));
      return Array.isArray(parsed) ? parsed : [];
    } catch (_) {
      return [];
    }
  }

  function _replaceProjectRunCompareOptions(select, options, selectedValue = '') {
    if (!select) return;
    select.replaceChildren();
    (Array.isArray(options) ? options : []).forEach((item) => {
      const option = document.createElement('option');
      option.value = String(item && item.value || '');
      option.textContent = String(item && item.label || item && item.value || '');
      select.appendChild(option);
    });
    const normalizedSelected = String(selectedValue || '');
    if (normalizedSelected && [...select.options].some(option => option.value === normalizedSelected)) {
      select.value = normalizedSelected;
    } else if (select.options.length) {
      select.value = select.options[0].value;
    }
  }

  function _projectRunCompareOptionLabels(option) {
    return Array.isArray(option && option.labels)
      ? option.labels.map(label => String(label || '').trim()).filter(Boolean)
      : [];
  }

  function _avoidProjectRunCompareLabelSelfTarget(container, label) {
    const leftSelect = container?.querySelector?.('[data-project-compare-run="left"]');
    if (!leftSelect || !label) return;
    const runOptions = _projectRunCompareDatasetOptions(container, 'projectCompareRunOptions');
    const selected = runOptions.find(option => String(option && option.value || '') === String(leftSelect.value || ''));
    if (!selected || !_projectRunCompareOptionLabels(selected).includes(label)) return;
    const fallback = runOptions.find(option => !_projectRunCompareOptionLabels(option).includes(label));
    if (!fallback) return;
    leftSelect.value = String(fallback.value || '');
    if (typeof global.syncAppSelect === 'function') {
      global.syncAppSelect(leftSelect);
    }
  }

  function _syncProjectRunCompareMode(wrap) {
    const container = wrap || projectExplorerBody?.querySelector('.project-run-compare-controls');
    if (!container) return;
    const mode = String(container.querySelector('[data-project-compare-mode]')?.value || 'run');
    const targetSelect = container.querySelector('[data-project-compare-target]');
    if (!targetSelect) return;
    const previousMode = String(targetSelect.dataset.projectCompareTargetMode || '');
    if (previousMode === 'run') targetSelect.dataset.projectCompareRunValue = targetSelect.value;
    if (previousMode === 'baseline') targetSelect.dataset.projectCompareBaselineValue = targetSelect.value;
    const options = mode === 'baseline'
      ? _projectRunCompareDatasetOptions(container, 'projectCompareLabelOptions')
      : _projectRunCompareDatasetOptions(container, 'projectCompareRunOptions');
    const savedValue = mode === 'baseline'
      ? targetSelect.dataset.projectCompareBaselineValue
      : targetSelect.dataset.projectCompareRunValue;
    _replaceProjectRunCompareOptions(targetSelect, options, savedValue);
    targetSelect.dataset.projectCompareTargetMode = mode;
    targetSelect.setAttribute('aria-label', mode === 'baseline' ? 'Baseline label' : 'Run baseline');
    if (mode === 'baseline') {
      _avoidProjectRunCompareLabelSelfTarget(container, String(targetSelect.value || ''));
    }
    if (typeof global.syncAppSelect === 'function') {
      global.syncAppSelect(targetSelect);
    }
    container.querySelectorAll('[data-project-compare-mode-value]').forEach((btn) => {
      const active = String(btn.dataset.projectCompareModeValue || '') === mode;
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }

  function _setProjectRunCompareMode(modeButton, event = null) {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    const controls = modeButton?.closest?.('.project-run-compare-controls');
    const modeInput = controls?.querySelector('[data-project-compare-mode]');
    if (!controls || !modeInput) return;
    modeInput.value = String(modeButton.dataset.projectCompareModeValue || 'run');
    _syncProjectRunCompareMode(controls);
  }

  function _renderProjectRunCompareControls(runs) {
    const wrap = document.createElement('div');
    wrap.className = 'project-run-compare-controls';
    const leftSelect = document.createElement('select');
    leftSelect.className = 'form-select form-control-compact project-run-compare-select';
    leftSelect.dataset.projectCompareRun = 'left';
    leftSelect.setAttribute('aria-label', 'Run to compare');
    const modeInput = document.createElement('input');
    modeInput.type = 'hidden';
    modeInput.dataset.projectCompareMode = '1';
    modeInput.value = 'run';
    const targetSelect = document.createElement('select');
    targetSelect.className = 'form-select form-control-compact project-run-compare-select';
    targetSelect.dataset.projectCompareTarget = '1';
    targetSelect.setAttribute('aria-label', 'Run baseline');
    const runOptions = [];
    runs.forEach((run, index) => {
      [leftSelect].forEach((select) => {
        const option = document.createElement('option');
        option.value = String(run.id || '');
        option.textContent = _projectRunCompareOptionText(run);
        select.appendChild(option);
      });
      runOptions.push({
        value: String(run.id || ''),
        label: _projectRunCompareOptionText(run),
        labels: _entityLabelValues(run),
      });
      if (index === 0) leftSelect.value = String(run.id || '');
      if (index === 1) targetSelect.dataset.projectCompareRunValue = String(run.id || '');
    });
    const baselineLabels = _projectRunBaselineLabelOptions(runs);
    const baselineOptions = baselineLabels.map(label => ({ value: label, label }));
    targetSelect.dataset.projectCompareBaselineValue = baselineLabels.includes('baseline') ? 'baseline' : (baselineLabels[0] || '');
    wrap.dataset.projectCompareRunOptions = JSON.stringify(runOptions);
    wrap.dataset.projectCompareLabelOptions = JSON.stringify(baselineOptions);
    const modeGroup = document.createElement('div');
    modeGroup.className = 'project-run-compare-mode-group';
    modeGroup.setAttribute('role', 'group');
    modeGroup.setAttribute('aria-label', 'Compare against');
    modeGroup.hidden = !baselineLabels.length;
    [
      ['run', 'Run'],
      ['baseline', 'Label'],
    ].forEach(([value, label]) => {
      if (value === 'baseline' && !baselineLabels.length) return;
      const modeBtn = document.createElement('button');
      modeBtn.type = 'button';
      modeBtn.className = 'toggle-btn project-run-compare-mode-button';
      modeBtn.dataset.projectCompareModeValue = value;
      modeBtn.setAttribute('aria-pressed', value === modeInput.value ? 'true' : 'false');
      modeBtn.textContent = label;
      modeBtn.addEventListener('click', event => _setProjectRunCompareMode(modeBtn, event));
      _bindProjectRuntimePressable(modeBtn);
      modeGroup.appendChild(modeBtn);
    });
    wrap.append(leftSelect, modeInput, modeGroup, targetSelect);
    _syncProjectRunCompareMode(wrap);
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

  function _projectFilterDropdown(label, count, optionNodes) {
    const dropdown = document.createElement('div');
    dropdown.className = 'project-target-filter-menu project-shared-filter-menu';
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'control-row form-control-compact project-target-filter-trigger';
    trigger.setAttribute('aria-haspopup', 'menu');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.textContent = count ? `${label} (${count})` : label;
    dropdown.appendChild(trigger);

    const menu = document.createElement('div');
    menu.className = 'project-target-filter-options dropdown-surface';
    menu.setAttribute('role', 'menu');
    menu.hidden = true;
    if (optionNodes.length) {
      optionNodes.forEach(node => menu.appendChild(node));
    } else {
      const empty = document.createElement('div');
      empty.className = 'project-target-filter-empty';
      empty.textContent = 'No options available';
      menu.appendChild(empty);
    }
    dropdown.appendChild(menu);
    _bindProjectRuntimePressable(trigger, {
      onActivate: (event) => {
        event?.preventDefault?.();
        event?.stopPropagation?.();
        const open = !dropdown.classList.contains('is-open');
        _closeProjectFilterMenus(open ? dropdown : null);
        _setProjectFilterMenuOpen(dropdown, open);
      },
    });
    return dropdown;
  }

  function _setProjectFilterMenuOpen(menu, open) {
    if (!menu) return;
    menu.classList.toggle('is-open', !!open);
    const trigger = menu.querySelector('.project-target-filter-trigger');
    if (trigger) trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
    const panel = menu.querySelector('.project-target-filter-options');
    if (panel) panel.hidden = !open;
  }

  function _closeProjectFilterMenus(exceptMenu = null) {
    if (!projectWorkspaceModal) return;
    projectWorkspaceModal.querySelectorAll('.project-target-filter-menu.is-open').forEach((menu) => {
      if (exceptMenu && menu === exceptMenu) return;
      _setProjectFilterMenuOpen(menu, false);
    });
  }

  function _projectFilterOption({ labelText, value, checked, dataset }) {
    const label = document.createElement('label');
    label.className = 'project-target-filter-option dropdown-item dropdown-item-compact';
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
    chip.className = 'chip chip-removable project-target-filter-chip';
    chip.dataset.projectId = projectId;
    chip.dataset[clearAttr] = value;
    chip.textContent = `${label} ×`;
    _bindProjectRuntimePressable(chip);
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
    const selectedLabels = new Set(_projectFindingLabelFilterValues(projectId));
    let sortControl = null;
    if (projectWorkspaceTab === 'findings') {
      const statusOptions = FINDING_REVIEW_STATES.map(({ value, label: labelText }) => _projectFilterOption({
        labelText,
        value,
        checked: selectedStatuses.has(value),
        dataset: { projectFindingStatusFilterOption: '1', projectId },
      }));
      controls.appendChild(_projectFilterDropdown('Filter by status', selectedStatuses.size, statusOptions));

      const sortWrap = document.createElement('label');
      sortWrap.className = 'project-finding-sort-control project-finding-source-order-control';
      const sortSelect = document.createElement('select');
      sortSelect.className = 'form-select project-finding-sort-select';
      sortSelect.dataset.projectFindingSort = '1';
      sortSelect.dataset.projectId = projectId;
      sortSelect.setAttribute('aria-label', 'Sort findings');
      const currentSort = _projectFindingSortValue(projectId);
      PROJECT_FINDING_SORT_OPTIONS.forEach(({ value, label: labelText }) => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = labelText;
        option.selected = value === currentSort;
        sortSelect.appendChild(option);
      });
      sortWrap.appendChild(sortSelect);
      sortControl = sortWrap;
    }

    const labelOptions = _projectFindingLabelOptions(projectId).map(labelText => _projectFilterOption({
      labelText,
      value: labelText,
      checked: selectedLabels.has(labelText),
      dataset: { projectFindingLabelFilterOption: '1', projectId },
    }));
    controls.appendChild(_projectFilterDropdown('Filter by label', selectedLabels.size, labelOptions));

    const noteWrap = document.createElement('label');
    noteWrap.className = 'project-finding-sort-control project-finding-note-state-control';
    const noteSelect = document.createElement('select');
    noteSelect.className = 'form-select project-finding-note-state-select';
    noteSelect.dataset.projectFindingNoteState = '1';
    noteSelect.dataset.projectId = projectId;
    noteSelect.setAttribute('aria-label', 'Filter findings by notes');
    const currentNoteState = _projectFindingNoteStateValue(projectId);
    PROJECT_FINDING_NOTE_STATE_OPTIONS.forEach(({ value, label: labelText }) => {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = labelText;
      option.selected = value === currentNoteState;
      noteSelect.appendChild(option);
    });
    noteWrap.appendChild(noteSelect);
    controls.appendChild(noteWrap);
    if (sortControl) controls.appendChild(sortControl);
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
    selectedLabels.forEach((labelValue) => {
      chips.appendChild(_projectFilterChip({
        projectId,
        label: `label: ${labelValue}`,
        value: labelValue,
        clearAttr: 'projectFindingLabelFilterClear',
      }));
    });
    const noteState = _projectFindingNoteStateValue(projectId);
    if (noteState !== 'all') {
      const option = PROJECT_FINDING_NOTE_STATE_OPTIONS.find(item => item.value === noteState);
      chips.appendChild(_projectFilterChip({
        projectId,
        label: `notes: ${option ? option.label : noteState}`,
        value: noteState,
        clearAttr: 'projectFindingNoteStateClear',
      }));
    }
    const hasFilters = selectedTargets.size || selectedRuns.size || selectedStatuses.size
      || selectedLabels.size || noteState !== 'all';
    if (hasFilters) {
      const clearAll = document.createElement('button');
      clearAll.type = 'button';
      clearAll.className = 'btn btn-ghost btn-compact project-target-filter-clear';
      clearAll.dataset.projectFilterClearAll = '1';
      clearAll.dataset.projectId = projectId;
      clearAll.textContent = 'Clear filters';
      _bindProjectRuntimePressable(clearAll);
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

  function _projectFilterControlsRoot(root) {
    if (!root) return null;
    if (root.matches?.('.project-explorer-filter-controls')) return root;
    return root.querySelector?.('.project-explorer-filter-controls') || null;
  }

  function _projectFilterControlsShareRow(left, right) {
    if (!left || !right) return false;
    const leftRect = left.getBoundingClientRect();
    const rightRect = right.getBoundingClientRect();
    const tolerance = Math.max(2, Math.min(leftRect.height || 0, rightRect.height || 0) * 0.25);
    return Math.abs(leftRect.top - rightRect.top) <= tolerance;
  }

  function _syncProjectFilterSortDivider(root) {
    const controls = _projectFilterControlsRoot(root || projectExplorerBody);
    if (!controls) return;
    const noteControl = controls.querySelector('.project-finding-note-state-control');
    const sortControl = controls.querySelector('.project-finding-source-order-control');
    if (!sortControl) return;
    sortControl.classList.remove('has-sort-divider');
    if (!noteControl) return;
    if (_projectFilterControlsShareRow(noteControl, sortControl)) {
      sortControl.classList.add('has-sort-divider');
      if (!_projectFilterControlsShareRow(noteControl, sortControl)) {
        sortControl.classList.remove('has-sort-divider');
      }
    }
  }

  function _scheduleProjectFilterSortDividerSync(root) {
    projectFilterSortDividerSyncRoot = root || projectExplorerBody;
    if (projectFilterSortDividerSyncScheduled) return;
    projectFilterSortDividerSyncScheduled = true;
    const schedule = typeof global.requestAnimationFrame === 'function'
      ? global.requestAnimationFrame.bind(global)
      : (typeof window.requestAnimationFrame === 'function'
        ? window.requestAnimationFrame.bind(window)
        : window.setTimeout.bind(window));
    schedule(() => {
      projectFilterSortDividerSyncScheduled = false;
      _syncProjectFilterSortDivider(projectFilterSortDividerSyncRoot || projectExplorerBody);
    });
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
    let findings = _projectFilteredFindingItems(projectId, summary);
    if (!projectWorkspaceFilteredFindings.has(_projectFindingFilteredKey(projectId, summary))) {
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
      const labelFilters = new Set(_projectFindingLabelFilterValues(projectId));
      if (labelFilters.size) {
        findings = findings.filter(finding => _entityLabelValues(finding).some(label => labelFilters.has(label)));
      }
      const noteState = _projectFindingNoteStateValue(projectId);
      if (noteState === 'noted') findings = findings.filter(finding => !!_entityNoteBody(finding));
      else if (noteState === 'unnoted') findings = findings.filter(finding => !_entityNoteBody(finding));
    }
    return _sortProjectFindings(findings, projectId, summary);
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
    if (!normalized || projectWorkspaceFindings.has(normalized)) return;
    if (projectWorkspaceFindingsLoadingId === normalized && projectWorkspaceFindingsLoadingPromise) {
      return projectWorkspaceFindingsLoadingPromise;
    }
    projectWorkspaceFindingsLoadingId = normalized;
    projectWorkspaceFindingsLoadingPromise = Promise.resolve().then(async () => {
      _renderProjectExplorer();
      try {
        const resp = await apiFetch(`/projects/${encodeURIComponent(normalized)}/findings`, { cache: 'no-store' });
        if (!resp.ok) throw await _projectResponseError(resp, 'Could not load project findings.');
        const data = await resp.json();
        projectWorkspaceFindings.set(normalized, Array.isArray(data.findings) ? data.findings : []);
      } catch (err) {
        projectWorkspaceFindings.set(normalized, []);
        _setProjectWorkspaceMessage(err && err.message ? err.message : 'Could not load project findings.', { error: true });
        if (typeof logClientError === 'function') logClientError('failed to load project findings', err);
      } finally {
        if (projectWorkspaceFindingsLoadingId === normalized) {
          projectWorkspaceFindingsLoadingId = '';
          projectWorkspaceFindingsLoadingPromise = null;
        }
        _renderProjectExplorer();
        if (_projectPackageWizardActive(normalized)) {
          _renderProjectPackageWizardModal();
        }
      }
    });
    return projectWorkspaceFindingsLoadingPromise;
  }

  async function _loadProjectFilteredFindings(projectId, summary = _projectSummary(projectId)) {
    const normalized = String(projectId || '');
    const key = _projectFindingFilteredKey(normalized, summary);
    if (!normalized || !key || projectWorkspaceFilteredFindings.has(key) || projectWorkspaceFilteredFindingsLoadingKey === key) return;
    const params = _projectFindingServerFilterParams(normalized, summary);
    projectWorkspaceFilteredFindingsLoadingKey = key;
    try {
      const query = params.toString();
      const url = `/projects/${encodeURIComponent(normalized)}/findings${query ? `?${query}` : ''}`;
      const resp = await apiFetch(url, { cache: 'no-store' });
      if (!resp.ok) throw await _projectResponseError(resp, 'Could not load filtered project findings.');
      const data = await resp.json();
      projectWorkspaceFilteredFindings.set(
        key,
        Array.isArray(data.findings) ? data.findings : _filteredProjectFindings(normalized, summary),
      );
    } catch (err) {
      projectWorkspaceFilteredFindings.set(key, _filteredProjectFindings(normalized, summary));
      _setProjectWorkspaceMessage(
        err && err.message ? err.message : 'Could not load filtered project findings.',
        { error: true },
      );
      if (typeof logClientError === 'function') logClientError('failed to load filtered project findings', err);
    } finally {
      if (projectWorkspaceFilteredFindingsLoadingKey === key) projectWorkspaceFilteredFindingsLoadingKey = '';
      _renderProjectExplorer();
    }
  }

  function _syncProjectForms(project = _selectedProject()) {
    const hasProject = !!(project && project.id);
    const showingDetails = projectWorkspaceTab === 'details';
    const nextProjectId = hasProject ? String(project.id || '') : '';
    if (!showingDetails || String(projectLabelsInput?.dataset.projectId || '') !== nextProjectId) {
      _hideProjectLabelsSavedIndicator();
    }
    if (projectNotesForm) projectNotesForm.classList.toggle('u-hidden', !hasProject || !showingDetails);
    if (projectLabelsForm) projectLabelsForm.classList.toggle('u-hidden', !hasProject || !showingDetails);
    if (projectLabelsInput && document.activeElement !== projectLabelsInput) {
      projectLabelsInput.value = hasProject ? _entityLabelValues(project).join(', ') : '';
      projectLabelsInput.dataset.projectId = nextProjectId;
      projectLabelsInput.dataset.savedLabels = projectLabelsInput.value;
      projectLabelsInput.placeholder = hasProject
        ? `Labels for ${_projectDisplayName(project)}`
        : 'Select a project to edit labels';
    }
    const notesProjectId = String(projectNotesInput?.dataset.projectId || '');
    const hasPendingNotesEdit = !!projectNotesSaveTimer && notesProjectId === nextProjectId;
    if (projectNotesInput && document.activeElement !== projectNotesInput && !hasPendingNotesEdit) {
      projectNotesInput.value = hasProject ? _entityNoteBody(project) : '';
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

  function _setProjectLabelsSavedIndicator(visible) {
    if (!projectLabelsSaveStatus) return;
    projectLabelsSaveStatus.classList.toggle('u-hidden', !visible);
  }

  function _hideProjectLabelsSavedIndicator() {
    if (projectLabelsSavedHideTimer) {
      clearTimeout(projectLabelsSavedHideTimer);
      projectLabelsSavedHideTimer = null;
    }
    _setProjectLabelsSavedIndicator(false);
  }

  function _showProjectLabelsSavedIndicator(projectId) {
    const normalizedProjectId = String(projectId || '');
    _hideProjectLabelsSavedIndicator();
    if (normalizedProjectId && String(projectLabelsInput?.dataset.projectId || '') !== normalizedProjectId) return;
    _setProjectLabelsSavedIndicator(true);
    projectLabelsSavedHideTimer = setTimeout(() => {
      projectLabelsSavedHideTimer = null;
      _setProjectLabelsSavedIndicator(false);
    }, PROJECT_LABELS_SAVED_VISIBLE_MS);
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

  function _cacheProjectLabels(projectId, labels) {
    const normalizedProjectId = String(projectId || '');
    const labelItems = (Array.isArray(labels) ? labels : []).map(label => ({ label: String(label || '').trim() })).filter(item => item.label);
    if (!normalizedProjectId) return;
    const update = project => (
      String(project && project.id || '') === normalizedProjectId
        ? { ...project, labels: labelItems }
        : project
    );
    projectWorkspaceRows = projectWorkspaceRows.map(update);
    const summary = projectWorkspaceSummaries.get(normalizedProjectId);
    if (summary && summary.project) {
      projectWorkspaceSummaries.set(normalizedProjectId, {
        ...summary,
        project: update(summary.project),
      });
    }
    if (activeProject && String(activeProject.id || '') === normalizedProjectId) {
      activeProject = update(activeProject);
    }
  }

  async function _saveProjectLabelsNow() {
    if (!projectLabelsInput) return;
    const projectId = String(projectLabelsInput.dataset.projectId || projectWorkspaceSelectedId || '');
    if (!projectId) return;
    const labels = EntityMetadataClient.parseLabelInput(projectLabelsInput.value);
    const labelText = labels.join(', ');
    if (labelText === String(projectLabelsInput.dataset.savedLabels || '')) return;
    if (projectLabelsSaveButton) projectLabelsSaveButton.disabled = true;
    _hideProjectLabelsSavedIndicator();
    try {
      await _syncEntityLabels('project', projectId, labels);
      projectLabelsInput.value = labelText;
      projectLabelsInput.dataset.savedLabels = labelText;
      _cacheProjectLabels(projectId, labels);
      _renderProjectList();
      _renderProjectExplorer();
      _showProjectLabelsSavedIndicator(projectId);
    } catch (err) {
      _setProjectWorkspaceMessage(err.message || 'Could not save project labels.', { error: true });
    } finally {
      if (projectLabelsSaveButton) projectLabelsSaveButton.disabled = false;
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

  function _makeProjectButton(label, action, projectId, role = 'secondary', tone = '') {
    const btn = document.createElement('button');
    btn.type = 'button';
    const classes = ['btn', `btn-${role || 'secondary'}`, 'btn-compact'];
    if (tone) classes.push(`btn-${tone}`);
    btn.className = classes.join(' ');
    btn.textContent = label;
    btn.dataset.projectAction = action;
    if (projectId) btn.dataset.projectId = projectId;
    _bindProjectRuntimePressable(btn);
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
    row.className = 'control-row project-workspace-row'
      + (projectId === activeId ? ' is-active' : '')
      + (projectId === projectWorkspaceSelectedId ? ' is-selected' : '');
    row.dataset.projectId = projectId;
    row.dataset.projectAction = 'select';
    _bindProjectRuntimePressable(row);

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
    _appendProjectLabelChips(main, project, { className: 'project-workspace-label-chips' });
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

  function _projectTabCountText(projectId, summary, tabId, total) {
    const totalCount = Number(total || 0);
    const targetFiltersActive = _projectTargetFilterActive(projectId, summary);
    const runFiltersActive = _projectRunFilterActive(projectId, summary);

    if (tabId === 'findings') {
      if (!_projectFindingServerFiltersActive(projectId, summary) || !_projectFindingsLoaded(projectId)) {
        return String(totalCount);
      }
      return `${_filteredProjectFindings(projectId, summary).length}/${totalCount}`;
    }

    if (tabId === 'runs') {
      if (!targetFiltersActive && !runFiltersActive) return String(totalCount);
      if (targetFiltersActive && !_projectFindingsLoaded(projectId)) return String(totalCount);
      return `${_filteredProjectRuns(projectId, summary).length}/${totalCount}`;
    }

    if (tabId === 'artifacts') {
      if (!targetFiltersActive && !runFiltersActive) return String(totalCount);
      if (targetFiltersActive && !_projectFindingsLoaded(projectId)) return String(totalCount);
      return `${_filteredProjectArtifacts(projectId, summary).length}/${totalCount}`;
    }

    return String(totalCount);
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
    _appendProjectLabelChips(titleWrap, project);

    const activeId = activeProject && activeProject.id ? String(activeProject.id) : '';
    const actions = document.createElement('div');
    actions.className = 'project-explorer-actions';
    if (String(project.id || '') === activeId) {
      const pill = document.createElement('span');
      pill.className = 'project-explorer-active-pill';
      pill.textContent = 'active';
      actions.appendChild(pill);
      actions.appendChild(_makeProjectButton('Clear active', 'clear', String(project.id || '')));
    } else if (project.status !== 'archived') {
      actions.appendChild(_makeProjectButton('Use as active', 'use', String(project.id || '')));
    }
    if (project.status !== 'archived') {
      actions.appendChild(_makeProjectButton('Archive', 'archive', String(project.id || '')));
    } else {
      actions.appendChild(_makeProjectButton('Unarchive', 'unarchive', String(project.id || '')));
    }
    actions.appendChild(_makeProjectButton('Delete', 'delete', String(project.id || ''), 'destructive'));
    header.append(titleWrap, actions);

    const tabs = document.createElement('div');
    tabs.className = 'project-explorer-tabs';
    const tabCounts = _projectCounts(summary);
    const projectId = String(project.id || '');
    const tabItems = [
      { id: 'details', label: 'Details' },
      { id: 'runs', label: 'Runs', count: _projectTabCountText(projectId, summary, 'runs', tabCounts.runs) },
      { id: 'findings', label: 'Findings', count: _projectTabCountText(projectId, summary, 'findings', tabCounts.findings) },
      { id: 'artifacts', label: 'Artifacts', count: _projectTabCountText(projectId, summary, 'artifacts', tabCounts.artifacts) },
      { id: 'packages', label: 'Packages', count: tabCounts.packages },
    ];
    tabItems.forEach(({ id, label, count }) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'nav-item project-explorer-tab' + (projectWorkspaceTab === id ? ' is-active' : '');
      btn.dataset.projectTab = id;
      btn.textContent = count === undefined ? label : `${label} (${count})`;
      _bindProjectRuntimePressable(btn);
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

    const labelsSection = document.createElement('section');
    labelsSection.className = 'project-explorer-section project-explorer-labels-section';
    const labelsHeading = document.createElement('div');
    labelsHeading.className = 'project-explorer-section-heading project-labels-heading';
    const labelsTitle = document.createElement('h3');
    labelsTitle.textContent = 'Labels';
    labelsHeading.appendChild(labelsTitle);
    if (projectLabelsSaveStatus) labelsHeading.appendChild(projectLabelsSaveStatus);
    labelsSection.appendChild(labelsHeading);
    if (projectLabelsForm) labelsSection.appendChild(projectLabelsForm);
    container.appendChild(labelsSection);

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
    notesSection.className = 'project-explorer-section project-explorer-notes-section';
    const notesTitle = document.createElement('h3');
    notesTitle.textContent = 'Notes';
    notesSection.appendChild(notesTitle);
    if (projectNotesForm) notesSection.appendChild(projectNotesForm);
    container.appendChild(notesSection);
  }

  function _renderProjectRuns(container, projectId, summary) {
    const allRuns = _projectRunItems(summary);
    const comparableRuns = _projectComparableRuns(summary);
    const filterActive = _projectTargetFilterActive(projectId, summary);
    const toolbar = document.createElement('div');
    toolbar.className = 'project-runs-toolbar';
    toolbar.appendChild(_renderProjectRunCompareControls(comparableRuns));
    const toolbarActions = document.createElement('div');
    toolbarActions.className = 'project-runs-toolbar-actions';
    const compare = _makeProjectButton('Compare runs', 'compare-runs', projectId, comparableRuns.length >= 2 ? 'secondary' : 'ghost');
    compare.disabled = comparableRuns.length < 2;
    if (compare.disabled) {
      compare.title = 'Link two runs to compare.';
      compare.setAttribute('aria-disabled', 'true');
    } else {
      compare.title = 'Compare selected project runs.';
      compare.removeAttribute('aria-disabled');
    }
    const actionDivider = document.createElement('span');
    actionDivider.className = 'project-runs-toolbar-divider';
    actionDivider.setAttribute('aria-hidden', 'true');
    toolbarActions.append(compare, actionDivider, _makeProjectButton('Link last run', 'link-last-run', projectId));
    toolbar.appendChild(toolbarActions);
    container.appendChild(toolbar);
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
        chips: _entityMetadataChips(run),
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
      const message = _projectFindingServerFiltersActive(projectId, summary)
        ? 'No findings match the selected filters.'
        : 'No persisted findings for linked runs yet.';
      container.appendChild(_emptyProjectPanel(message));
      return;
    }
    _groupBy(findings, finding => finding.run_command || finding.run_id).forEach((items, runLabel) => {
      const group = document.createElement('section');
      group.className = 'project-explorer-group project-findings-group';
      const collapsed = _projectFindingGroupCollapsed(projectId, runLabel);
      group.classList.toggle('is-collapsed', collapsed);
      const title = document.createElement('button');
      title.type = 'button';
      title.className = 'toggle-btn project-explorer-group-toggle';
      title.dataset.projectFindingGroupToggle = '1';
      title.dataset.projectId = projectId;
      title.dataset.projectFindingGroup = runLabel;
      title.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
      _bindProjectRuntimePressable(title);
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
          _projectFindingTargetText(summary, finding) || _projectTargetLabel(summary, finding.target_id),
          `line ${finding.line_number || 0}`,
        ].filter(Boolean);
        body.appendChild(_projectItemRow({
          title: finding.title || finding.raw_line,
          meta: metaParts.join(' · '),
          detail: finding.raw_line || '',
          badge: finding.review_state || finding.severity || '',
          chips: _entityMetadataChips(finding),
          accessory: _findingRowAccessory(finding, projectId),
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
      group.className = 'project-explorer-group project-artifacts-group';
      const run = _projectRunById(summary, runId);
      const command = String(run?.command || '').trim();
      const shortId = _shortProjectRunId(runId);
      const collapsed = _projectArtifactGroupCollapsed(projectId, runId);
      group.classList.toggle('is-collapsed', collapsed);
      const title = document.createElement('button');
      title.type = 'button';
      title.className = 'toggle-btn project-explorer-group-toggle';
      title.dataset.projectArtifactGroupToggle = '1';
      title.dataset.projectId = projectId;
      title.dataset.projectArtifactGroup = String(runId || '');
      title.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
      _bindProjectRuntimePressable(title);
      const caret = document.createElement('span');
      caret.className = 'project-explorer-group-caret';
      caret.setAttribute('aria-hidden', 'true');
      caret.textContent = '▾';
      const label = document.createElement('span');
      label.className = 'project-explorer-group-title';
      label.textContent = `${command || 'Run'}${shortId ? ` (${shortId})` : ''}`;
      const count = document.createElement('span');
      count.className = 'project-explorer-group-count';
      count.textContent = `${items.length} artifact${items.length === 1 ? '' : 's'}`;
      title.append(caret, label, count);
      group.appendChild(title);
      const body = document.createElement('div');
      body.className = 'project-explorer-group-body';
      body.hidden = collapsed;
      items.forEach((artifact) => {
        body.appendChild(_projectItemRow({
          title: artifact.display_name || artifact.workspace_path,
          meta: artifact.workspace_path,
          detail: _projectArtifactDetail(artifact),
          chips: _entityMetadataChips(artifact),
          accessory: _projectArtifactAccessory(projectId, artifact),
        }));
      });
      group.appendChild(body);
      container.appendChild(group);
    });
  }

  function _renderProjectPackages(container, projectId, summary) {
    const toolbar = document.createElement('div');
    toolbar.className = 'project-package-toolbar';
    const newBtn = _makeProjectButton('New package', 'package-wizard-open', projectId);
    toolbar.appendChild(newBtn);
    container.appendChild(toolbar);
    const packages = _projectPackageItems(summary);
    if (!packages.length) {
      container.appendChild(_emptyProjectPanel('No evidence packages yet.'));
      return;
    }
    packages.forEach((pkg) => {
      const counts = _projectPackageCountsText(pkg);
      const updated = _formatProjectDate(pkg.updated);
      const detail = [pkg.description || '', counts, updated ? `Updated ${updated}` : '']
        .filter(Boolean)
        .join(' · ');
      container.appendChild(_projectItemRow({
        title: pkg.name,
        meta: _projectPackageMetaText(pkg),
        detail,
        chips: _entityMetadataChips(pkg),
        accessory: _projectPackageAccessory(projectId, pkg),
      }));
    });
  }

  function _renderProjectExplorer() {
    if (!projectExplorerBody) return;
    projectExplorerBody.classList.toggle('project-explorer-body-details', projectWorkspaceTab === 'details');
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
    const filterBar = _renderProjectFilterBar(projectId, summary);
    projectExplorerBody.append(header, filterBar, tabs);
    const content = document.createElement('div');
    content.className = 'project-explorer-tab-panel';
    if (projectWorkspaceTab === 'details') {
      content.classList.add('project-explorer-tab-panel-details');
      _renderProjectDetails(content, project, summary);
    } else if (projectWorkspaceTab === 'runs') _renderProjectRuns(content, projectId, summary);
    else if (projectWorkspaceTab === 'findings') _renderProjectFindings(content, projectId, summary);
    else if (projectWorkspaceTab === 'artifacts') _renderProjectArtifacts(content, projectId, summary);
    else if (projectWorkspaceTab === 'packages') _renderProjectPackages(content, projectId, summary);
    projectExplorerBody.appendChild(content);
    if (typeof global.enhanceAppSelects === 'function') {
      global.enhanceAppSelects(content);
      global.enhanceAppSelects(filterBar);
    }
    _syncProjectFilterSortDivider(filterBar);
    _scheduleProjectFilterSortDividerSync(filterBar);
    if (
      projectWorkspaceTab === 'findings'
      || ['runs', 'artifacts'].includes(projectWorkspaceTab)
      || _projectPackageWizardActive(projectId)
      || _projectTargetFilterActive(projectId, summary)
      || !_projectFindingsLoaded(projectId)
    ) {
      _loadProjectFindings(projectId).catch(() => {});
    }
    if (
      projectWorkspaceTab === 'findings'
      && _projectFindingsLoaded(projectId)
      && _projectFindingServerFiltersActive(projectId, summary)
    ) {
      _loadProjectFilteredFindings(projectId, summary).catch(() => {});
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
    _renderProjectPackageWizardModal();
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

  function _scheduleProjectWorkspaceExternalRefresh() {
    if (!isProjectWorkspaceOpen()) return;
    if (projectWorkspaceExternalRefreshTimer) clearTimeout(projectWorkspaceExternalRefreshTimer);
    projectWorkspaceExternalRefreshTimer = setTimeout(() => {
      projectWorkspaceExternalRefreshTimer = null;
      refreshProjectWorkspace().catch(() => {});
    }, 250);
  }

  function _notifyProjectWorkspaceChanged(reason = 'updated', projectId = '', { local = true } = {}) {
    const payload = {
      reason: String(reason || 'updated'),
      project_id: String(projectId || ''),
      ts: Date.now(),
      nonce: Math.random().toString(36).slice(2),
    };
    if (typeof emitUiEvent === 'function') emitUiEvent('app:project-workspace-mutated', payload);
    if (local) _scheduleProjectWorkspaceExternalRefresh();
    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem(PROJECT_WORKSPACE_BROADCAST_KEY, JSON.stringify(payload));
      }
    } catch (_) {}
  }

  if (typeof document !== 'undefined' && typeof document.addEventListener === 'function') {
    document.addEventListener('app:project-target-discovered', (event) => {
      const detail = event && event.detail && typeof event.detail === 'object' ? event.detail : {};
      const count = Number(detail.count || detail.target_count || 0);
      if (!Number.isFinite(count) || count <= 0) return;
      _pulseProjectNavTargets();
      if (typeof showToast === 'function') showToast(_projectTargetDiscoveryMessage(count));
      if (isProjectWorkspaceOpen()) {
        refreshProjectWorkspace().catch(() => {});
      }
    });
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
    _closeProjectEntityEditor();
    _closeProjectPackageManifest();
    _closeProjectPackageWizard({ render: false });
    _hideProjectWorkspaceOverlay();
    _setProjectWorkspaceMessage('');
    if (refocus && typeof refocusComposerAfterAction === 'function') {
      refocusComposerAfterAction({ defer: true });
    }
  }

  async function _projectWorkspaceRequest(url, options = {}) {
    return EntityMetadataClient.entityMetadataRequest(url, options, {
      onWrite: () => _notifyProjectWorkspaceChanged('write', projectWorkspaceSelectedId, { local: false }),
    });
  }

  async function _syncEntityLabels(entityType, entityId, nextLabels) {
    await EntityMetadataClient.syncEntityLabels(entityType, entityId, nextLabels, {
      request: _projectWorkspaceRequest,
    });
  }

  async function _syncEntityNote(entityType, entityId, body) {
    await EntityMetadataClient.syncEntityNote(entityType, entityId, body, {
      request: _projectWorkspaceRequest,
    });
  }

  async function _saveProjectEntityMetadata() {
    if (!projectWorkspaceEditingEntity || !projectEntityLabelsInput || !projectEntityNoteInput) return;
    const { projectId, entityType, entityId, onSaved } = projectWorkspaceEditingEntity;
    const labels = EntityMetadataClient.parseLabelInput(projectEntityLabelsInput.value);
    const noteBody = String(projectEntityNoteInput.value || '').trim();
    if (projectEntitySubmitButton) projectEntitySubmitButton.disabled = true;
    try {
      await _syncEntityLabels(entityType, entityId, labels);
      await _syncEntityNote(entityType, entityId, noteBody);
      _closeProjectEntityEditor();
      if (typeof onSaved === 'function') {
        await onSaved({ entityType, entityId, labels, noteBody });
      } else {
        await refreshProjectWorkspace();
        if (entityType === 'finding' && projectId) {
          _invalidateProjectFindings(projectId);
          await _loadProjectFindings(projectId);
        }
        _renderProjectExplorer();
        const label = _entityEditorLabelForType(entityType).toLocaleLowerCase();
        _setProjectWorkspaceMessage(`${label.charAt(0).toLocaleUpperCase()}${label.slice(1)} metadata saved.`);
      }
    } finally {
      if (projectEntitySubmitButton) projectEntitySubmitButton.disabled = false;
    }
  }

  async function _linkLastRunToProject(projectId, summary) {
    const normalizedProjectId = String(projectId || projectWorkspaceSelectedId || '').trim();
    if (!normalizedProjectId) throw new Error('Select or create a project before linking runs.');
    const linkedRunIds = new Set(_projectRunItems(summary).map(run => String(run && run.id || '')).filter(Boolean));
    const resp = await apiFetch('/history?type=runs&page_size=25', { cache: 'no-store' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const candidates = Array.isArray(data.runs) ? data.runs : (Array.isArray(data.items) ? data.items : []);
    const run = candidates.find(item => {
      const runId = String(item && item.id || '');
      return runId && !linkedRunIds.has(runId) && (!item.type || item.type === 'run');
    });
    if (!run) throw new Error('No unlinked recent run found.');
    await _projectWorkspaceRequest(`/projects/${encodeURIComponent(normalizedProjectId)}/links`, {
      method: 'POST',
      body: JSON.stringify({
        entity_type: 'run',
        entity_id: String(run.id || ''),
        source: 'manual',
      }),
    });
    await refreshProjectWorkspace();
    _setProjectWorkspaceMessage('Last run linked to this project.');
  }

  async function _confirmProjectDestructive({ body, actionLabel, actionId, note }) {
    const confirmFn = typeof showConfirm === 'function'
      ? showConfirm
      : (global && typeof global.showConfirm === 'function' ? global.showConfirm : null);
    if (!confirmFn) {
      throw new Error('Project destructive confirmations require showConfirm.');
    }
    const choice = await confirmFn({
      body: note ? { text: body, note } : body,
      tone: 'danger',
      actions: [
        { id: 'cancel', label: 'Cancel', role: 'cancel' },
        { id: actionId, label: actionLabel, role: 'destructive' },
      ],
    });
    return choice === actionId;
  }

  function _confirmProjectTargetDelete(targetValue) {
    const label = String(targetValue || 'this target');
    return _confirmProjectDestructive({
      body: `Remove target ${label}?`,
      actionLabel: 'Remove',
      actionId: 'remove',
    });
  }

  function _confirmProjectRunUnlink(runCommand) {
    const label = String(runCommand || 'this run');
    return _confirmProjectDestructive({
      body: `Remove run from project: ${label}?`,
      actionLabel: 'Remove',
      actionId: 'remove',
    });
  }

  function _confirmProjectPackageDelete(packageName) {
    const label = String(packageName || 'this package');
    return _confirmProjectDestructive({
      body: `Delete package: ${label}?`,
      actionLabel: 'Delete',
      actionId: 'delete',
    });
  }

  function _confirmProjectDelete(projectName) {
    const label = String(projectName || 'this project');
    return _confirmProjectDestructive({
      body: `Delete project: ${label}?`,
      note: 'This removes the project, its targets, packages, and project links. Source runs and saved history remain.',
      actionLabel: 'Delete',
      actionId: 'delete',
    });
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

  projectTargetNotesInput?.addEventListener('input', () => {
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
    const notesValidationError = _projectTargetNotesValidationError(payload.notes);
    if (notesValidationError) {
      _setProjectTargetValueError(notesValidationError, { target: 'notes' });
      if (projectTargetNotesInput) {
        projectTargetNotesInput.focus();
      }
      return;
    }
    try {
      const metadata = _projectTargetEditorMetadata();
      const url = targetId
        ? `/projects/${encodeURIComponent(projectId)}/targets/${encodeURIComponent(targetId)}`
        : `/projects/${encodeURIComponent(projectId)}/targets`;
      const resp = await _projectWorkspaceRequest(url, {
        method: targetId ? 'PUT' : 'POST',
        body: JSON.stringify(payload),
      });
      const data = await resp.json().catch(() => ({}));
      const savedTargetId = targetId || String(data && data.target && data.target.id || '');
      if (!savedTargetId) {
        throw new Error('Target saved without an identifier.');
      }
      await _syncEntityLabels('target', savedTargetId, metadata.labels);
      await _syncEntityNote('target', savedTargetId, metadata.noteBody);
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

  projectEntityEditorForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      await _saveProjectEntityMetadata();
    } catch (err) {
      _setProjectWorkspaceMessage(err.message || 'Could not save metadata.', { error: true });
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

  function _handleProjectPackageWizardInput(event) {
    const packageField = event.target.closest?.('[data-project-package-field]');
    if (!packageField || !projectPackageWizard) return false;
    const field = String(packageField.dataset.projectPackageField || '');
    if (field === 'name') projectPackageWizard.name = String(packageField.value || '');
    if (field === 'description') projectPackageWizard.description = String(packageField.value || '');
    if (field === 'labels') projectPackageWizard.labels = String(packageField.value || '');
    if (field === 'notes') projectPackageWizard.notes = String(packageField.value || '');
    if (field === 'redaction_mode') {
      const mode = String(packageField.value || 'raw') === 'redacted' ? 'redacted' : 'raw';
      projectPackageWizard.redactionMode = mode;
      if (mode === 'redacted') projectPackageWizard.includeArtifacts = false;
      projectPackageWizard.notice = '';
      _renderProjectPackageWizardModal();
    }
    return true;
  }

  projectWorkspaceModal?.addEventListener('input', (event) => {
    _handleProjectPackageWizardInput(event);
  });

  projectNotesForm?.addEventListener('submit', (event) => {
    event.preventDefault();
    _flushProjectNotesAutosave().catch(() => {});
  });

  projectLabelsInput?.addEventListener('input', () => {
    _hideProjectLabelsSavedIndicator();
  });

  projectLabelsForm?.addEventListener('submit', (event) => {
    event.preventDefault();
    _saveProjectLabelsNow().catch(() => {});
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
    _invalidateProjectFilteredFindings(normalizedProjectId);
  }

  function _handleProjectPackageWizardChange(event) {
    if (_handleProjectPackageWizardInput(event)) return true;
    const packagePreset = event.target.closest?.('[data-project-package-preset]');
    if (packagePreset && projectPackageWizard) {
      event.stopPropagation();
      const projectId = String(packagePreset.dataset.projectId || projectPackageWizard.projectId || '');
      const preset = String(packagePreset.value || 'evidence');
      _openProjectPackageWizard(projectId, preset);
      return true;
    }
    const packageSelection = event.target.closest?.('[data-project-package-selection]');
    if (packageSelection && projectPackageWizard) {
      event.stopPropagation();
      const scrollTop = projectPackageWizardBody
        ?.querySelector('.project-package-wizard-body')
        ?.scrollTop ?? null;
      const kind = String(packageSelection.dataset.projectPackageSelection || '');
      const selected = _packageWizardSetFor(kind);
      const value = String(packageSelection.value || '');
      if (packageSelection.checked) selected.add(value);
      else selected.delete(value);
      if (kind === 'run') {
        const transcriptRuns = _packageWizardSetFor('transcript');
        const childIds = _packageWizardRunChildIds(value, projectPackageWizard.projectId, _projectSummary(projectPackageWizard.projectId));
        const findingIds = _packageWizardSetFor('finding');
        const artifactIds = _packageWizardSetFor('artifact');
        if (packageSelection.checked) {
          transcriptRuns.add(value);
          childIds.findingIds.forEach(id => findingIds.add(id));
          childIds.artifactIds.forEach(id => artifactIds.add(id));
        } else {
          transcriptRuns.delete(value);
          childIds.findingIds.forEach(id => findingIds.delete(id));
          childIds.artifactIds.forEach(id => artifactIds.delete(id));
        }
      } else if (packageSelection.checked && ['transcript', 'finding', 'artifact'].includes(kind)) {
        const runId = String(packageSelection.dataset.runId || (kind === 'transcript' ? value : ''));
        if (runId) _packageWizardSetFor('run').add(runId);
      }
      projectPackageWizard.notice = '';
      _renderProjectPackageWizardModal({ scrollTop });
      return true;
    }
    const packagePrivateNotes = event.target.closest?.('[data-project-package-private-notes]');
    if (packagePrivateNotes && projectPackageWizard) {
      event.stopPropagation();
      const scrollTop = projectPackageWizardBody
        ?.querySelector('.project-package-wizard-body')
        ?.scrollTop ?? null;
      projectPackageWizard.includePrivateNotes = !!packagePrivateNotes.checked;
      projectPackageWizard.notice = '';
      _renderProjectPackageWizardModal({ scrollTop });
      return true;
    }
    const packageIncludeArtifacts = event.target.closest?.('[data-project-package-include-artifacts]');
    if (packageIncludeArtifacts && projectPackageWizard) {
      event.stopPropagation();
      const scrollTop = projectPackageWizardBody
        ?.querySelector('.project-package-wizard-body')
        ?.scrollTop ?? null;
      projectPackageWizard.includeArtifacts = !!packageIncludeArtifacts.checked;
      projectPackageWizard.notice = '';
      _renderProjectPackageWizardModal({ scrollTop });
      return true;
    }
    return false;
  }

  projectWorkspaceModal?.addEventListener('change', async (event) => {
    if (_handleProjectPackageWizardChange(event)) return;
    const compareModeControl = event.target.closest?.('[data-project-compare-mode]');
    if (compareModeControl) {
      event.stopPropagation();
      _syncProjectRunCompareMode(compareModeControl.closest('.project-run-compare-controls'));
      return;
    }
    const compareControl = event.target.closest?.('[data-project-compare-target], [data-project-compare-run="left"]');
    if (compareControl) {
      const controls = compareControl.closest('.project-run-compare-controls');
      if (String(controls?.querySelector('[data-project-compare-mode]')?.value || 'run') === 'baseline') {
        _avoidProjectRunCompareLabelSelfTarget(controls, String(controls?.querySelector('[data-project-compare-target]')?.value || ''));
      }
      return;
    }
    const sortControl = event.target.closest?.('[data-project-finding-sort]');
    if (sortControl) {
      event.stopPropagation();
      const projectId = String(sortControl.dataset.projectId || projectWorkspaceSelectedId || '');
      if (!projectId) return;
      projectWorkspaceFindingSort.set(projectId, String(sortControl.value || 'run'));
      _renderProjectExplorer();
      return;
    }
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
    const labelFilterControl = event.target.closest?.('[data-project-finding-label-filter-option]');
    if (labelFilterControl) {
      event.stopPropagation();
      const projectId = String(labelFilterControl.dataset.projectId || projectWorkspaceSelectedId || '');
      const labelValue = String(labelFilterControl.value || '').trim();
      if (!projectId || !labelValue) return;
      const filters = _projectFindingLabelFilterSet(projectId);
      if (labelFilterControl.checked) filters.add(labelValue);
      else filters.delete(labelValue);
      _renderProjectExplorer();
      return;
    }
    const noteStateControl = event.target.closest?.('[data-project-finding-note-state]');
    if (noteStateControl) {
      event.stopPropagation();
      const projectId = String(noteStateControl.dataset.projectId || projectWorkspaceSelectedId || '');
      if (!projectId) return;
      const value = String(noteStateControl.value || 'all');
      if (value === 'all') projectWorkspaceFindingNoteStateFilters.delete(projectId);
      else projectWorkspaceFindingNoteStateFilters.set(projectId, value);
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

  document.addEventListener('click', (event) => {
    if (!isProjectWorkspaceOpen()) return;
    const menu = event.target.closest?.('.project-target-filter-menu');
    if (menu && projectWorkspaceModal?.contains(menu)) {
      _closeProjectFilterMenus(menu);
      return;
    }
    _closeProjectFilterMenus();
  }, true);

  async function _handleProjectPackageWizardAction(btn) {
    if (!btn) return false;
    const action = String(btn.dataset.projectAction || '');
    if (!action.startsWith('package-wizard-')) return false;
    const projectId = String(btn.dataset.projectId || projectPackageWizard?.projectId || '');
    if (action === 'package-wizard-open') {
      _openProjectPackageWizard(projectId, 'evidence');
      return true;
    }
    if (action === 'package-wizard-cancel') {
      _closeProjectPackageWizard();
      return true;
    }
    if (action === 'package-wizard-preset') {
      const preset = String(btn.dataset.preset || 'evidence');
      _openProjectPackageWizard(projectId, preset);
      return true;
    }
    if (action === 'package-wizard-back') {
      if (projectPackageWizard) {
        projectPackageWizard.step = Math.max(1, projectPackageWizard.step - 1);
        projectPackageWizard.notice = '';
      }
      _renderProjectPackageWizardModal();
      return true;
    }
    if (action === 'package-wizard-next') {
      if (!projectPackageWizard) return true;
      if (projectPackageWizard.step >= 4) {
        await _createProjectPackageFromWizard(projectId);
        return true;
      }
      projectPackageWizard.step = Math.min(4, projectPackageWizard.step + 1);
      projectPackageWizard.notice = '';
      _setProjectWorkspaceMessage('');
      _renderProjectPackageWizardModal();
      return true;
    }
    return false;
  }

  projectWorkspaceModal?.addEventListener('click', async (event) => {
    if (event.target.closest?.('[data-project-review-state]')) return;
    const compareModeButton = event.target.closest?.('[data-project-compare-mode-value]');
    if (compareModeButton) {
      _setProjectRunCompareMode(compareModeButton, event);
      return;
    }
    const messageDismiss = event.target.closest?.('[data-project-message-dismiss]');
    if (messageDismiss) {
      event.preventDefault();
      event.stopPropagation();
      _setProjectWorkspaceMessage('');
      return;
    }
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
    const artifactGroupToggle = event.target.closest?.('[data-project-artifact-group-toggle]');
    if (artifactGroupToggle) {
      event.preventDefault();
      event.stopPropagation();
      const projectId = String(artifactGroupToggle.dataset.projectId || projectWorkspaceSelectedId || '');
      const runId = String(artifactGroupToggle.dataset.projectArtifactGroup || '');
      const key = _projectArtifactGroupKey(projectId, runId);
      if (projectWorkspaceCollapsedArtifactGroups.has(key)) {
        projectWorkspaceCollapsedArtifactGroups.delete(key);
      } else {
        projectWorkspaceCollapsedArtifactGroups.add(key);
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
    const labelFilterClear = event.target.closest?.('[data-project-finding-label-filter-clear]');
    if (labelFilterClear) {
      event.preventDefault();
      event.stopPropagation();
      const projectId = String(labelFilterClear.dataset.projectId || projectWorkspaceSelectedId || '');
      const labelValue = String(labelFilterClear.dataset.projectFindingLabelFilterClear || '');
      const filters = _projectFindingLabelFilterSet(projectId);
      if (labelValue === 'all') filters.clear();
      else if (labelValue) filters.delete(labelValue);
      _renderProjectExplorer();
      return;
    }
    const noteStateClear = event.target.closest?.('[data-project-finding-note-state-clear]');
    if (noteStateClear) {
      event.preventDefault();
      event.stopPropagation();
      const projectId = String(noteStateClear.dataset.projectId || projectWorkspaceSelectedId || '');
      if (projectId) projectWorkspaceFindingNoteStateFilters.delete(projectId);
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
      _projectFindingLabelFilterSet(projectId).clear();
      projectWorkspaceFindingNoteStateFilters.delete(projectId);
      _renderProjectExplorer();
      return;
    }
    const tabBtn = event.target.closest?.('[data-project-tab]');
    if (tabBtn) {
      event.preventDefault();
      await _flushProjectNotesAutosave();
      projectWorkspaceTab = tabBtn.dataset.projectTab || 'details';
      if (projectWorkspaceTab !== 'details') _closeProjectTargetEditor();
      _closeProjectEntityEditor();
      _setProjectWorkspaceMessage('');
      _renderProjectExplorer();
      return;
    }
    const btn = event.target.closest?.('[data-project-action]');
    if (!btn) return;
    if (btn.getAttribute('role') === 'button' && event.target.closest?.('select, input, textarea, a, button')) return;
    event.preventDefault();
    const action = btn.dataset.projectAction || '';
    const projectId = btn.dataset.projectId || '';
    let successMessage = '';
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
        successMessage = 'Active project updated.';
      } else if (action === 'clear') {
        await _projectWorkspaceRequest('/projects/active', { method: 'DELETE' });
        successMessage = 'Active project cleared.';
      } else if (action === 'archive') {
        await _projectWorkspaceRequest(`/projects/${encodeURIComponent(projectId)}`, {
          method: 'PUT',
          body: JSON.stringify({ status: 'archived' }),
        });
        if (activeProject && String(activeProject.id || '') === projectId) {
          await _projectWorkspaceRequest('/projects/active', { method: 'DELETE' });
        }
        successMessage = 'Project archived.';
      } else if (action === 'unarchive') {
        await _projectWorkspaceRequest(`/projects/${encodeURIComponent(projectId)}`, {
          method: 'PUT',
          body: JSON.stringify({ status: 'active' }),
        });
        successMessage = 'Project unarchived.';
      } else if (action === 'delete') {
        const project = projectWorkspaceRows.find(item => String(item.id || '') === projectId) || null;
        const confirmed = await _confirmProjectDelete(project ? _projectDisplayName(project) : projectId);
        if (!confirmed) return;
        await _projectWorkspaceRequest(`/projects/${encodeURIComponent(projectId)}`, { method: 'DELETE' });
        if (projectWorkspaceSelectedId === projectId) {
          projectWorkspaceSelectedId = '';
          _closeProjectTargetEditor();
        }
        await refreshProjectWorkspace();
        _setProjectWorkspaceMessage('Project deleted.');
        return;
      } else if (action === 'new-target') {
        _setProjectWorkspaceMessage('');
        _openProjectTargetEditor(projectId);
        return;
      } else if (await _handleProjectPackageWizardAction(btn)) {
        return;
      } else if (action === 'edit-target') {
        const targetId = String(btn.dataset.targetId || '');
        const summary = projectWorkspaceSummaries.get(String(projectId || ''));
        const target = _projectTargetItems(summary).find(item => String(item.id || '') === targetId);
        if (!target) throw new Error('Target is missing its details.');
        _setProjectWorkspaceMessage('');
        _openProjectTargetEditor(projectId, target);
        return;
      } else if (action === 'edit-finding-metadata') {
        const findingId = String(btn.dataset.findingId || '');
        const finding = _projectFindingItems(projectId).find(item => String(item.id || '') === findingId);
        if (!finding) throw new Error('Finding is missing its details.');
        _setProjectWorkspaceMessage('');
        _openProjectEntityEditor(projectId, 'finding', finding);
        return;
      } else if (action === 'edit-run-metadata') {
        const runId = String(btn.dataset.runId || '');
        const summary = projectWorkspaceSummaries.get(String(projectId || ''));
        const run = _projectRunItems(summary).find(item => String(item.id || '') === runId);
        if (!run) throw new Error('Run is missing its details.');
        _setProjectWorkspaceMessage('');
        _openProjectEntityEditor(projectId, 'run', run);
        return;
      } else if (action === 'edit-artifact-metadata') {
        const artifactId = String(btn.dataset.artifactId || '');
        const summary = projectWorkspaceSummaries.get(String(projectId || ''));
        const artifact = _projectArtifactItems(summary).find(item => String(item.id || '') === artifactId);
        if (!artifact) throw new Error('Artifact is missing its details.');
        _setProjectWorkspaceMessage('');
        _openProjectEntityEditor(projectId, 'run_file_artifact', artifact);
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
      } else if (action === 'confirm-target' || action === 'dismiss-target') {
        const targetId = String(btn.dataset.targetId || '');
        if (!projectId || !targetId) throw new Error('Target is missing its identifier.');
        const reviewState = action === 'confirm-target' ? 'confirmed' : 'dismissed';
        await _projectWorkspaceRequest(`/projects/${encodeURIComponent(projectId)}/targets/${encodeURIComponent(targetId)}`, {
          method: 'PUT',
          body: JSON.stringify({ review_state: reviewState }),
        });
        await refreshProjectWorkspace();
        if (typeof loadProjectAutocompleteTargets === 'function') {
          loadProjectAutocompleteTargets().catch(() => {});
        }
        _setProjectWorkspaceMessage(reviewState === 'confirmed' ? 'Target confirmed.' : 'Target dismissed.');
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
      } else if (action === 'compare-runs') {
        const controls = projectExplorerBody?.querySelector('.project-run-compare-controls');
        const mode = String(projectExplorerBody?.querySelector('[data-project-compare-mode]')?.value || 'run');
        const targetValue = String(projectExplorerBody?.querySelector('[data-project-compare-target]')?.value || '').trim();
        if (mode === 'baseline') {
          _avoidProjectRunCompareLabelSelfTarget(controls, targetValue);
        }
        const leftId = String(projectExplorerBody?.querySelector('[data-project-compare-run="left"]')?.value || '');
        if (!projectId || !leftId) throw new Error('Choose a project run to compare.');
        if (mode === 'run' && !targetValue) throw new Error('Choose two project runs to compare.');
        if (mode === 'run' && leftId === targetValue) throw new Error('Choose two different project runs to compare.');
        if (mode === 'baseline' && !targetValue) throw new Error('Choose a baseline label to compare.');
        const compareFn = global && typeof global.fetchAndRenderHistoryComparison === 'function'
          ? global.fetchAndRenderHistoryComparison
          : (typeof window !== 'undefined' && typeof window.fetchAndRenderHistoryComparison === 'function'
              ? window.fetchAndRenderHistoryComparison
              : null);
        if (!compareFn) throw new Error('Run comparison is not available.');
        const params = new URLSearchParams({ left_run_id: leftId });
        if (mode === 'baseline') params.set('baseline_label', targetValue);
        else params.set('right_run_id', targetValue);
        compareFn(leftId, mode === 'baseline' ? `baseline:${targetValue}` : targetValue, {
          url: `/projects/${encodeURIComponent(projectId)}/compare?${params.toString()}`,
        });
        return;
      } else if (action === 'link-last-run') {
        await _linkLastRunToProject(projectId, projectWorkspaceSummaries.get(String(projectId || '')));
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
      } else if (
        action === 'package-edit'
        || action === 'package-download'
        || action === 'package-repackage'
        || action === 'package-manifest'
        || action === 'package-delete'
      ) {
        const packageId = String(btn.dataset.packageId || '').trim();
        if (!projectId || !packageId) throw new Error('Package is missing its identifier.');
        const summary = projectWorkspaceSummaries.get(String(projectId || ''));
        const pkg = _projectPackageById(summary, packageId) || { id: packageId, name: packageId };
        if (action === 'package-edit') {
          _openProjectEntityEditor(projectId, 'package', pkg);
          return;
        }
        if (action === 'package-download') {
          _setProjectPackageDownloadBusy(btn, true);
          try {
            await _downloadProjectPackage(projectId, pkg);
          } finally {
            _setProjectPackageDownloadBusy(btn, false);
          }
          return;
        }
        if (action === 'package-repackage' || action === 'package-manifest') {
          const resp = await _projectWorkspaceRequest(
            `/projects/${encodeURIComponent(projectId)}/packages/${encodeURIComponent(packageId)}`,
            { cache: 'no-store' },
          );
          const data = await resp.json().catch(() => ({}));
          if (action === 'package-repackage') {
            _openProjectPackageWizardFromPackage(projectId, data.package || pkg);
            return;
          }
          _openProjectPackageManifest(data.package || pkg);
          return;
        }
        const confirmed = await _confirmProjectPackageDelete(pkg.name || packageId);
        if (!confirmed) return;
        await _projectWorkspaceRequest(`/projects/${encodeURIComponent(projectId)}/packages/${encodeURIComponent(packageId)}`, {
          method: 'DELETE',
        });
        _closeProjectPackageManifest();
        await refreshProjectWorkspace();
        _setProjectWorkspaceMessage('Package deleted.');
        return;
      }
      await refreshProjectWorkspace();
      if (successMessage) _setProjectWorkspaceMessage(successMessage);
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

  projectEntityEditorOverlay?.querySelector('.project-entity-editor-close')?.addEventListener('click', () => {
    _closeProjectEntityEditor();
  });

  projectEntityEditorOverlay?.querySelector('.project-entity-editor-cancel')?.addEventListener('click', () => {
    _closeProjectEntityEditor();
  });

  projectPackageWizardOverlay?.addEventListener('input', (event) => {
    _handleProjectPackageWizardInput(event);
  });

  projectPackageWizardOverlay?.addEventListener('change', (event) => {
    _handleProjectPackageWizardChange(event);
  });

  projectPackageWizardOverlay?.addEventListener('click', async (event) => {
    const runToggle = event.target.closest?.('[data-project-package-run-toggle]');
    if (runToggle && projectPackageWizard) {
      event.preventDefault();
      event.stopPropagation();
      const scrollTop = projectPackageWizardBody
        ?.querySelector('.project-package-wizard-body')
        ?.scrollTop ?? null;
      const runId = String(runToggle.dataset.runId || '');
      if (runId) {
        if (!projectPackageWizard.collapsedRunIds) projectPackageWizard.collapsedRunIds = new Set();
        if (projectPackageWizard.collapsedRunIds.has(runId)) projectPackageWizard.collapsedRunIds.delete(runId);
        else projectPackageWizard.collapsedRunIds.add(runId);
      }
      _renderProjectPackageWizardModal({ scrollTop });
      return;
    }
    const btn = event.target.closest?.('[data-project-action]');
    if (!btn) return;
    event.preventDefault();
    try {
      await _handleProjectPackageWizardAction(btn);
    } catch (err) {
      _setProjectWorkspaceMessage(err.message || 'Package action failed.', { error: true });
      if (projectPackageWizard) {
        projectPackageWizard.notice = err.message || 'Package action failed.';
        projectPackageWizard.noticeError = true;
        _renderProjectPackageWizardModal();
      }
    }
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
  if (bindDismissibleFn && projectEntityEditorOverlay) {
    bindDismissibleFn(projectEntityEditorOverlay, {
      level: 'modal',
      isOpen: isProjectEntityEditorOpen,
      onClose: () => _closeProjectEntityEditor(),
      closeButtons: null,
    });
  }
  if (bindDismissibleFn && projectPackageWizardOverlay) {
    bindDismissibleFn(projectPackageWizardOverlay, {
      level: 'modal',
      isOpen: isProjectPackageWizardOpen,
      onClose: () => _closeProjectPackageWizard(),
      closeButtons: null,
    });
  }
  if (bindDismissibleFn && projectPackageManifestOverlay) {
    bindDismissibleFn(projectPackageManifestOverlay, {
      level: 'modal',
      isOpen: isProjectPackageManifestOpen,
      onClose: () => _closeProjectPackageManifest(),
      closeButtons: [projectPackageManifestOverlay.querySelector('.project-package-manifest-close')],
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
      return;
    }
    if (e.key === PROJECT_WORKSPACE_BROADCAST_KEY && e.newValue) {
      _scheduleProjectWorkspaceExternalRefresh();
    }
  });
  document.addEventListener('visibilitychange', () => {
    _startHudStatusPoll({ pollNow: document.visibilityState === 'visible' });
  });
  window.addEventListener('resize', () => {
    _scheduleProjectFilterSortDividerSync(projectExplorerBody);
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
  global.isProjectPackageManifestOpen = isProjectPackageManifestOpen;
  global.refreshProjectWorkspace = refreshProjectWorkspace;
  global.notifyProjectWorkspaceChanged = _notifyProjectWorkspaceChanged;

})(globalThis);
