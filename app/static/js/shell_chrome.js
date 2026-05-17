// ── Shell chrome controller ──
// Owns the desktop rail (Recent, Workflows, nav) and the bottom HUD.
// Loaded after dom.js, state.js, ui_helpers.js, history.js, tabs.js, app.js,
// project_details.js, project_list.js, project_navigation.js, project_entity_editor.js,
// project_active_context.js, project_workspace_constants.js, project_workspace_lifecycle.js, project_workspace_renderer.js, project_workspace_bootstrap.js, project_shared_ui.js, project_nested_sheets.js, project_mobile_compare.js, project_mobile_shell.js, project_mobile_detail.js,
// project_entities.js, project_findings.js, project_artifacts.js, project_packages.js, and controller.js
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
  const projectWorkspaceOverlay = document.getElementById('project-workspace-overlay');
  const projectWorkspaceModal = document.getElementById('project-workspace-modal');
  const projectWorkspaceBody = document.getElementById('project-workspace-body');
  const projectExplorerBody = document.getElementById('project-explorer-body');
  const projectWorkspaceSubtitle = document.getElementById('project-workspace-subtitle');
  const projectWorkspaceCreateForm = document.getElementById('project-workspace-create-form');
  const projectWorkspaceNameInput = document.getElementById('project-workspace-name');
  const projectMobileRoot = document.getElementById('project-mobile-root');
  const projectMobileListView = document.getElementById('project-mobile-list-view');
  const projectMobileBody = document.getElementById('project-mobile-body');
  const projectMobileSummary = document.getElementById('project-mobile-summary');
  const projectMobileCreateForm = document.getElementById('project-mobile-create-form');
  const projectMobileNameInput = document.getElementById('project-mobile-name');
  const projectMobileDetailView = document.getElementById('project-mobile-detail-view');
  const projectMobileDetailTopbar = document.getElementById('project-mobile-detail-topbar');
  const projectMobileTabs = document.getElementById('project-mobile-tabs');
  const projectMobileDetailBody = document.getElementById('project-mobile-detail-body');
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
  const PROJECT_TARGET_HELPERS = global.ProjectTargetValidation || window.ProjectTargetValidation;
  if (!PROJECT_TARGET_HELPERS) throw new Error('ProjectTargetValidation is unavailable');
  const PROJECT_TARGET_TYPES = PROJECT_TARGET_HELPERS.TARGET_TYPES;
  const PROJECT_WORKSPACE_CONSTANTS = global.DarklabProjectWorkspaceConstants || window.DarklabProjectWorkspaceConstants;
  if (!PROJECT_WORKSPACE_CONSTANTS) throw new Error('DarklabProjectWorkspaceConstants is unavailable');

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
  let projectWorkspaceRows = [];
  let projectWorkspaceSummaries = new Map();
  let projectWorkspaceLoading = false;
  let projectWorkspaceSelectedId = '';
  let projectWorkspaceTab = 'details';
  let projectWorkspaceEditingTargetId = '';
  let projectWorkspaceLastTargetType = 'domain';
  let projectWorkspaceCollapsedFindingGroups = new Set();
  let projectWorkspaceCollapsedArtifactGroups = new Set();
  let projectWorkspaceEntityTab = 'ip';
  let projectWorkspaceEntitySelectMode = false;
  let projectWorkspaceSelectedEntityIds = new Set();
  let projectWorkspaceFindingSelectMode = false;
  let projectWorkspaceSelectedFindingIds = new Set();
  let projectWorkspaceEntityPicker = null;
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
    if (action === 'atlas' && typeof global.openAtlas === 'function') {
      void global.openAtlas({ source: 'rail' });
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

  let projectSharedUiController = null;

  function _projectSharedUiController() {
    if (projectSharedUiController) return projectSharedUiController;
    const factory = global.DarklabProjectSharedUi && global.DarklabProjectSharedUi.createProjectSharedUiController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectSharedUi is unavailable');
    projectSharedUiController = factory({
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      downloadBlobAsAttachment,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
    });
    return projectSharedUiController;
  }

  function _projectDisplayName(project) {
    return _projectSharedUiController().displayName(project);
  }

  let projectActiveContextController = null;

  function _projectActiveContextController() {
    if (projectActiveContextController) return projectActiveContextController;
    const factory = global.DarklabProjectActiveContext
      && global.DarklabProjectActiveContext.createProjectActiveContextController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectActiveContext is unavailable');
    projectActiveContextController = factory({
      apiFetch,
      emitUiEvent: (eventName, detail) => {
        if (typeof emitUiEvent === 'function') emitUiEvent(eventName, detail);
      },
      hudProjectCell,
      hudProjectEl,
      isProjectWorkspaceOpen,
      logClientError: (message, err) => {
        if (typeof logClientError === 'function') logClientError(message, err);
      },
      projectDisplayName: _projectDisplayName,
      railNav,
      refreshProjectWorkspace,
      setValueColor: _setValueColor,
      showToast: typeof showToast === 'function' ? showToast : null,
      syncProjectNotesForm: _syncProjectNotesForm,
    });
    return projectActiveContextController;
  }

  function _activeProject() {
    return _projectActiveContextController().project();
  }

  function _setActiveProject(project) {
    return _projectActiveContextController().setProject(project);
  }

  function _renderActiveProject() {
    _projectActiveContextController().render();
  }

  async function loadActiveProjectContext() {
    return _projectActiveContextController().load();
  }

  let projectWorkspaceShellController = null;

  function _projectWorkspaceShellController() {
    if (projectWorkspaceShellController) return projectWorkspaceShellController;
    const factory = global.DarklabProjectWorkspaceShell
      && global.DarklabProjectWorkspaceShell.createProjectWorkspaceShellController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectWorkspaceShell is unavailable');
    projectWorkspaceShellController = factory({
      EntityMetadataClient,
      blurVisibleComposerInputIfMobile: () => {
        if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
      },
      closeMajorOverlays: () => {
        if (typeof global._closeMajorOverlays === 'function') global._closeMajorOverlays();
      },
      closeProjectEntityEditor: _closeProjectEntityEditor,
      closeProjectMobileActionSheet: _closeProjectMobileActionSheet,
      closeProjectMobileCompareSheet: _closeProjectMobileCompareSheet,
      closeProjectPackageManifest: _closeProjectPackageManifest,
      closeProjectPackageWizard: _closeProjectPackageWizard,
      closeProjectTargetEditor: _closeProjectTargetEditor,
      emitUiEvent: (eventName, detail) => {
        if (typeof emitUiEvent === 'function') emitUiEvent(eventName, detail);
      },
      flushProjectNotesAutosave: _flushProjectNotesAutosave,
      markInteractionSurfaceReady: (surfaceName, overlay, modal) => {
        if (typeof markInteractionSurfaceReady === 'function') markInteractionSurfaceReady(surfaceName, overlay, modal);
      },
      projectEntitiesController: _projectEntitiesController,
      projectWorkspaceBody,
      projectWorkspaceBroadcastKey: PROJECT_WORKSPACE_CONSTANTS.workspaceBroadcastKey,
      projectMobileCreateForm,
      projectMobileNameInput,
      projectWorkspaceCreateForm,
      projectWorkspaceMessage,
      projectWorkspaceModal,
      projectWorkspaceNameInput,
      projectWorkspaceOverlay,
      refocusComposerAfterAction: (options) => {
        if (typeof refocusComposerAfterAction === 'function') refocusComposerAfterAction(options);
      },
      refreshProjectWorkspace,
      selectedProjectId: () => projectWorkspaceSelectedId,
      setProjectMobileCreateOpen: _setProjectMobileCreateOpen,
      setProjectWorkspaceTab: (tab) => { projectWorkspaceTab = tab; },
      setSelectedProjectId: (projectId) => { projectWorkspaceSelectedId = String(projectId || ''); },
      showToast: typeof showToast === 'function' ? showToast : null,
    });
    return projectWorkspaceShellController;
  }

  let projectWorkspaceActionsController = null;

  function _projectWorkspaceActionsController() {
    if (projectWorkspaceActionsController) return projectWorkspaceActionsController;
    const factory = global.DarklabProjectWorkspaceActions
      && global.DarklabProjectWorkspaceActions.createProjectWorkspaceActionsController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectWorkspaceActions is unavailable');
    projectWorkspaceActionsController = factory({
      EntityMetadataClient,
      apiFetch,
      projectRunItems: _projectRunItems,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      refreshProjectWorkspace,
      selectedProjectId: () => projectWorkspaceSelectedId,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      showConfirm: typeof showConfirm === 'function' ? showConfirm : null,
    });
    return projectWorkspaceActionsController;
  }

  function isProjectWorkspaceOpen() {
    return _projectWorkspaceShellController().isOpen();
  }

  function _setProjectWorkspaceMessage(text = '', { error = false } = {}) {
    _projectWorkspaceShellController().setMessage(text, { error });
  }

  async function _projectResponseError(resp, fallback) {
    let message = fallback;
    try {
      const data = await resp.json();
      if (data && data.error) message = data.error;
    } catch (_) {}
    return new Error(message || fallback);
  }

  function _selectedProject() {
    return _projectWorkspaceLifecycleController().selectedProject();
  }

  function _projectSummary(projectId = projectWorkspaceSelectedId) {
    return _projectWorkspaceLifecycleController().projectSummary(projectId);
  }

  function _ensureSelectedProject() {
    _projectWorkspaceLifecycleController().ensureSelectedProject();
  }

  function _projectCounts(summary) {
    return _projectSharedUiController().counts(summary);
  }

  function _projectCountEntries(summary) {
    return _projectSharedUiController().countEntries(summary);
  }

  function _projectTargetItems(summary) {
    return _projectSharedUiController().targetItems(summary);
  }

  let projectEntitiesController = null;

  function _projectEntitiesController() {
    if (projectEntitiesController) return projectEntitiesController;
    const factory = global.DarklabProjectEntities && global.DarklabProjectEntities.createProjectEntitiesController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectEntities is unavailable');
    projectEntitiesController = factory({
      apiFetch,
      getSummary: projectId => projectWorkspaceSummaries.get(String(projectId || '')) || null,
      getActiveTab: () => projectWorkspaceEntityTab,
      setActiveTab: (tabId) => { projectWorkspaceEntityTab = tabId; },
      getSelectMode: () => projectWorkspaceEntitySelectMode,
      setSelectMode: (enabled) => { projectWorkspaceEntitySelectMode = !!enabled; },
      getSelectedIds: () => projectWorkspaceSelectedEntityIds,
      getPicker: () => projectWorkspaceEntityPicker,
      setPicker: (picker) => { projectWorkspaceEntityPicker = picker; },
      formatDate: _formatProjectDate,
      shortProjectRunId: _shortProjectRunId,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      projectMobileEmptyPanel: _projectMobileEmptyPanel,
      projectItemRow: _projectItemRow,
      projectMobileContentRow: _projectMobileContentRow,
      projectMobileActionMenu: _projectMobileActionMenu,
      entityMetadataChips: _entityMetadataChips,
      projectResponseError: _projectResponseError,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      refreshProjectWorkspace,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      downloadBlobAsAttachment: _downloadBlobAsAttachment,
      closeProjectWorkspace,
      openAtlas: global.openAtlas,
      projectDisplayName: _projectDisplayName,
      setWorkspaceTab: (tabId) => { projectWorkspaceTab = tabId; },
    });
    return projectEntitiesController;
  }

  let projectPackagesController = null;

  function _projectPackagesController() {
    if (projectPackagesController) return projectPackagesController;
    const factory = global.DarklabProjectPackages && global.DarklabProjectPackages.createProjectPackagesController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectPackages is unavailable');
    projectPackagesController = factory({
      apiFetch,
      EntityMetadataClient,
      manifestOverlay: projectPackageManifestOverlay,
      manifestTitle: projectPackageManifestTitle,
      manifestJson: projectPackageManifestJson,
      wizardOverlay: projectPackageWizardOverlay,
      wizardBody: projectPackageWizardBody,
      getSelectedProjectId: () => projectWorkspaceSelectedId,
      selectedProject: _selectedProject,
      projectSummary: _projectSummary,
      projectRunItems: _projectRunItems,
      projectArtifactItems: _projectArtifactItems,
      projectTargetItems: _projectTargetItems,
      projectFindingItems: _projectFindingItems,
      projectFindingsLoaded: _projectFindingsLoaded,
      loadProjectFindings: _loadProjectFindings,
      projectFilesEnabled: _projectFilesEnabled,
      projectArtifactStatus: _projectArtifactStatus,
      projectArtifactDetail: _projectArtifactDetail,
      projectTargetFilterLabel: _projectTargetFilterLabel,
      entityLabelValues: _entityLabelValues,
      entityNoteBody: _entityNoteBody,
      entityMetadataChips: _entityMetadataChips,
      formatDate: _formatProjectDate,
      formatBytes: _formatProjectBytes,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      projectMobileEmptyPanel: _projectMobileEmptyPanel,
      projectMobileContentRow: _projectMobileContentRow,
      projectMobileActionMenu: _projectMobileActionMenu,
      projectItemRow: _projectItemRow,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      refreshProjectWorkspace,
      renderProjectExplorer: _renderProjectExplorer,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      downloadBlobAsAttachment: _downloadBlobAsAttachment,
      setWorkspaceTab: (tabId) => { projectWorkspaceTab = tabId; },
      syncProjectWorkspaceNestedSuppression: _syncProjectWorkspaceNestedSuppression,
      focusProjectNestedSheet: _focusProjectNestedSheet,
      installProjectMobileKeyboardGuards: _installProjectMobileKeyboardGuards,
    });
    return projectPackagesController;
  }

  let projectFiltersController = null;

  function _projectFiltersController() {
    if (projectFiltersController) return projectFiltersController;
    const factory = global.DarklabProjectFilters && global.DarklabProjectFilters.createProjectFiltersController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectFilters is unavailable');
    projectFiltersController = factory({
      getSelectedProjectId: () => projectWorkspaceSelectedId,
      projectWorkspaceModal: () => projectWorkspaceModal,
      projectExplorerBody: () => projectExplorerBody,
      projectWorkspaceTab: () => projectWorkspaceTab,
      projectSummary: _projectSummary,
      findingReviewStates: PROJECT_WORKSPACE_CONSTANTS.findingReviewStates,
      findingSeverityRank: PROJECT_WORKSPACE_CONSTANTS.findingSeverityRank,
      findingReviewRank: PROJECT_WORKSPACE_CONSTANTS.findingReviewRank,
      projectFindingSortOptions: PROJECT_WORKSPACE_CONSTANTS.findingSortOptions,
      projectFindingNoteStateOptions: PROJECT_WORKSPACE_CONSTANTS.findingNoteStateOptions,
      projectFindingOrphanOptions: PROJECT_WORKSPACE_CONSTANTS.findingOrphanOptions,
      projectTargetItems: _projectTargetItems,
      projectTargetLabel: _projectTargetLabel,
      projectRunItems: _projectRunItems,
      projectRunById: _projectRunById,
      shortProjectRunId: _shortProjectRunId,
      projectFindingItems: _projectFindingItems,
      projectFilteredFindingItems: key => _projectFindingsDataController().filteredItems(key),
      hasProjectFilteredFindingsKey: key => _projectFindingsDataController().hasFilteredKey(key),
      projectArtifactItems: _projectArtifactItems,
      entityLabelValues: _entityLabelValues,
      entityNoteBody: _entityNoteBody,
      findingReviewStateLabel: _findingReviewStateLabel,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
    });
    return projectFiltersController;
  }

  let projectFindingsDataController = null;

  function _projectFindingsDataController() {
    if (projectFindingsDataController) return projectFindingsDataController;
    const factory = global.DarklabProjectFindingsData && global.DarklabProjectFindingsData.createProjectFindingsDataController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectFindingsData is unavailable');
    projectFindingsDataController = factory({
      apiFetch,
      selectedProjectId: () => projectWorkspaceSelectedId,
      mobileView: () => _projectMobileShellController().currentView(),
      projectSummary: _projectSummary,
      findingFilteredKey: _projectFindingFilteredKey,
      findingServerFilterParams: _projectFindingServerFilterParams,
      filteredProjectFindings: _filteredProjectFindings,
      projectResponseError: _projectResponseError,
      renderProjectExplorer: _renderProjectExplorer,
      renderProjectMobileDetail: _renderProjectMobileDetail,
      renderProjectPackageWizardModal: _renderProjectPackageWizardModal,
      projectPackageWizardActive: _projectPackageWizardActive,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      logClientError: (message, err) => {
        if (typeof logClientError === 'function') logClientError(message, err);
      },
    });
    return projectFindingsDataController;
  }

  let projectFindingsController = null;

  function _projectFindingsController() {
    if (projectFindingsController) return projectFindingsController;
    const factory = global.DarklabProjectFindings && global.DarklabProjectFindings.createProjectFindingsController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectFindings is unavailable');
    projectFindingsController = factory({
      findingReviewStates: PROJECT_WORKSPACE_CONSTANTS.findingReviewStates,
      collapsedFindingGroups: () => projectWorkspaceCollapsedFindingGroups,
      findingsLoadingId: () => _projectFindingsDataController().loadingId(),
      hasFindings: projectId => _projectFindingsDataController().loaded(projectId),
      findingSelectMode: () => projectWorkspaceFindingSelectMode,
      selectedFindingIds: () => projectWorkspaceSelectedFindingIds,
      projectFindingItems: _projectFindingItems,
      filteredProjectFindings: _filteredProjectFindings,
      projectFindingServerFiltersActive: _projectFindingServerFiltersActive,
      projectFindingTargetText: _projectFindingTargetText,
      projectTargetLabel: _projectTargetLabel,
      entityMetadataChips: _entityMetadataChips,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      projectItemRow: _projectItemRow,
      groupBy: _groupBy,
      metaSeparator: ' · ',
      groupCaret: '▾',
    });
    return projectFindingsController;
  }

  let projectArtifactsController = null;

  function _projectArtifactsController() {
    if (projectArtifactsController) return projectArtifactsController;
    const factory = global.DarklabProjectArtifacts && global.DarklabProjectArtifacts.createProjectArtifactsController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectArtifacts is unavailable');
    projectArtifactsController = factory({
      apiFetch,
      collapsedArtifactGroups: () => projectWorkspaceCollapsedArtifactGroups,
      filesEnabled: () => !!(typeof APP_CONFIG !== 'undefined' && APP_CONFIG && APP_CONFIG.workspace_enabled === true),
      projectTargetFilterActive: _projectTargetFilterActive,
      projectFindingsLoaded: _projectFindingsLoaded,
      filteredProjectArtifacts: _filteredProjectArtifacts,
      projectRunById: _projectRunById,
      shortProjectRunId: _shortProjectRunId,
      entityMetadataChips: _entityMetadataChips,
      formatDate: _formatProjectDate,
      formatBytes: _formatProjectBytes,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      projectItemRow: _projectItemRow,
      groupBy: _groupBy,
      downloadBlobAsAttachment: _downloadBlobAsAttachment,
      metaSeparator: ' · ',
      groupCaret: '▾',
    });
    return projectArtifactsController;
  }

  let projectDetailsController = null;

  function _projectDetailsController() {
    if (projectDetailsController) return projectDetailsController;
    const factory = global.DarklabProjectDetails && global.DarklabProjectDetails.createProjectDetailsController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectDetails is unavailable');
    projectDetailsController = factory({
      entityMetadataClient: EntityMetadataClient,
      projectNotesForm,
      projectNotesInput,
      projectNotesSaveStatus,
      projectLabelsForm,
      projectLabelsInput,
      projectLabelsSaveButton,
      projectLabelsSaveStatus,
      projectWorkspaceTab: () => projectWorkspaceTab,
      selectedProject: _selectedProject,
      selectedProjectId: () => projectWorkspaceSelectedId,
      projectRows: () => projectWorkspaceRows,
      setProjectRows: (rows) => { projectWorkspaceRows = Array.isArray(rows) ? rows : []; },
      projectSummary: _projectSummary,
      setProjectSummary: (projectId, summary) => { projectWorkspaceSummaries.set(String(projectId || ''), summary); },
      activeProject: _activeProject,
      setActiveProject: _setActiveProject,
      projectDisplayName: _projectDisplayName,
      projectTargetItems: _projectTargetItems,
      entityLabelValues: _entityLabelValues,
      entityNoteBody: _entityNoteBody,
      entityMetadataChipClass: _entityMetadataChipClass,
      projectMetaRow: _projectMetaRow,
      formatDate: _formatProjectDate,
      makeProjectButton: _makeProjectButton,
      renderProjectTargets: _renderProjectTargets,
      syncEntityLabels: _syncEntityLabels,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      renderProjectList: _renderProjectList,
      renderProjectExplorer: _renderProjectExplorer,
      renderActiveProject: _renderActiveProject,
      projectNotesAutosaveDelayMs: PROJECT_WORKSPACE_CONSTANTS.projectNotesAutosaveDelayMs,
      fieldSavedIndicatorDelayMs: PROJECT_WORKSPACE_CONSTANTS.fieldSavedIndicatorDelayMs,
      fieldSavedIndicatorVisibleMs: PROJECT_WORKSPACE_CONSTANTS.fieldSavedIndicatorVisibleMs,
      projectLabelsSavedVisibleMs: PROJECT_WORKSPACE_CONSTANTS.projectLabelsSavedVisibleMs,
    });
    return projectDetailsController;
  }

  let projectListController = null;

  function _projectListController() {
    if (projectListController) return projectListController;
    const factory = global.DarklabProjectList && global.DarklabProjectList.createProjectListController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectList is unavailable');
    projectListController = factory({
      projectWorkspaceBody,
      projectWorkspaceLoading: () => projectWorkspaceLoading,
      projectRows: () => projectWorkspaceRows,
      selectedProjectId: () => projectWorkspaceSelectedId,
      activeProject: _activeProject,
      projectSummary: _projectSummary,
      projectCountEntries: _projectCountEntries,
      projectArtifactsVisible: _projectArtifactsVisible,
      projectDisplayName: _projectDisplayName,
      appendProjectLabelChips: _appendProjectLabelChips,
      appendProjectMobileLabelChips: _appendProjectMobileLabelChips,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      mobileMenuText: '☰',
      mobileChevronText: '›',
    });
    return projectListController;
  }

  let projectNavigationController = null;

  function _projectNavigationController() {
    if (projectNavigationController) return projectNavigationController;
    const factory = global.DarklabProjectNavigation && global.DarklabProjectNavigation.createProjectNavigationController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectNavigation is unavailable');
    projectNavigationController = factory({
      projectWorkspaceModal,
      projectMobileDetailTopbar,
      projectMobileTabs,
      activeProject: _activeProject,
      projectWorkspaceTab: () => projectWorkspaceTab,
      setProjectWorkspaceTab: (tab) => { projectWorkspaceTab = tab; },
      projectCounts: _projectCounts,
      projectDisplayName: _projectDisplayName,
      projectIsArchived: _projectIsArchived,
      projectArtifactsVisible: _projectArtifactsVisible,
      projectTargetFilterActive: _projectTargetFilterActive,
      projectRunFilterActive: _projectRunFilterActive,
      projectFindingsLoaded: _projectFindingsLoaded,
      projectFindingServerFiltersActive: _projectFindingServerFiltersActive,
      filteredProjectFindings: _filteredProjectFindings,
      filteredProjectRuns: _filteredProjectRuns,
      filteredProjectArtifacts: _filteredProjectArtifacts,
      appendProjectLabelChips: _appendProjectLabelChips,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      syncProjectMobileActiveTabScroll: _syncProjectMobileActiveTabScroll,
      metaSeparator: ' · ',
      mobileBackText: '‹ Back',
    });
    return projectNavigationController;
  }

  let projectNestedSheetsController = null;

  function _projectNestedSheetsController() {
    if (projectNestedSheetsController) return projectNestedSheetsController;
    const factory = global.DarklabProjectNestedSheets && global.DarklabProjectNestedSheets.createProjectNestedSheetsController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectNestedSheets is unavailable');
    projectNestedSheetsController = factory({
      projectWorkspaceModal,
      projectTargetEditorOverlay,
      projectEntityEditorOverlay,
      projectPackageManifestOverlay,
      projectPackageWizardOverlay,
      isProjectTargetEditorOpen: () => !!(projectTargetEditorOverlay && projectTargetEditorOverlay.classList.contains('open')),
      isProjectEntityEditorOpen: () => !!(projectEntityEditorOverlay && projectEntityEditorOverlay.classList.contains('open')),
      isProjectPackageManifestOpen: () => !!(projectPackageManifestOverlay && projectPackageManifestOverlay.classList.contains('open')),
      isProjectPackageWizardOpen: () => !!(projectPackageWizardOverlay && projectPackageWizardOverlay.classList.contains('open')),
    });
    return projectNestedSheetsController;
  }

  let projectWorkspaceRendererController = null;

  function _projectWorkspaceRendererController() {
    if (projectWorkspaceRendererController) return projectWorkspaceRendererController;
    const factory = global.DarklabProjectWorkspaceRenderer
      && global.DarklabProjectWorkspaceRenderer.createProjectWorkspaceRendererController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectWorkspaceRenderer is unavailable');
    projectWorkspaceRendererController = factory({
      closeProjectEntityEditor: _closeProjectEntityEditor,
      closeProjectTargetEditor: _closeProjectTargetEditor,
      emptyProjectPanel: _emptyProjectPanel,
      enhanceAppSelects: typeof global.enhanceAppSelects === 'function' ? global.enhanceAppSelects : null,
      ensureSelectedProject: _ensureSelectedProject,
      flushProjectNotesAutosave: _flushProjectNotesAutosave,
      focusProjectWorkspaceTab: _focusProjectWorkspaceTab,
      isProjectWorkspaceOpen,
      loadProjectFilteredFindings: _loadProjectFilteredFindings,
      loadProjectFindings: _loadProjectFindings,
      mobileView: () => _projectMobileShellController().currentView(),
      projectArtifactsVisible: _projectArtifactsVisible,
      projectExplorerBody,
      projectFindingServerFiltersActive: _projectFindingServerFiltersActive,
      projectFindingsLoaded: _projectFindingsLoaded,
      projectMobileDetailBody,
      projectMobileTabItems: _projectMobileTabItems,
      projectPackageWizardActive: _projectPackageWizardActive,
      projectRows: () => projectWorkspaceRows,
      projectSummary: _projectSummary,
      projectTargetFilterActive: _projectTargetFilterActive,
      projectWorkspaceLoading: () => projectWorkspaceLoading,
      projectWorkspaceSubtitle,
      renderProjectArtifacts: _renderProjectArtifacts,
      renderProjectDetails: _renderProjectDetails,
      renderProjectEntities: _renderProjectEntities,
      renderProjectFilterBar: _renderProjectFilterBar,
      renderProjectFindings: _renderProjectFindings,
      renderProjectHeader: _renderProjectHeader,
      renderProjectList: _renderProjectList,
      renderProjectMobile: _renderProjectMobile,
      renderProjectPackages: _renderProjectPackages,
      renderProjectPackageWizardModal: _renderProjectPackageWizardModal,
      renderProjectRuns: _renderProjectRuns,
      scheduleProjectFilterSortDividerSync: _scheduleProjectFilterSortDividerSync,
      selectedProject: _selectedProject,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      setWorkspaceTab: (tabId) => { projectWorkspaceTab = tabId; },
      syncProjectFilterSortDivider: _syncProjectFilterSortDivider,
      syncProjectForms: _syncProjectForms,
      workspaceTab: () => projectWorkspaceTab,
    });
    return projectWorkspaceRendererController;
  }

  let projectWorkspaceBootstrapController = null;

  function _projectWorkspaceBootstrapController() {
    if (projectWorkspaceBootstrapController) return projectWorkspaceBootstrapController;
    const factory = global.DarklabProjectWorkspaceBootstrap
      && global.DarklabProjectWorkspaceBootstrap.createProjectWorkspaceBootstrapController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectWorkspaceBootstrap is unavailable');
    const bindDismissibleFn = global && typeof global.bindDismissible === 'function'
      ? global.bindDismissible
      : (typeof bindDismissible === 'function' ? bindDismissible : null);
    const bindMobileSheetFn = global && typeof global.bindMobileSheet === 'function'
      ? global.bindMobileSheet
      : (typeof bindMobileSheet === 'function' ? bindMobileSheet : null);
    projectWorkspaceBootstrapController = factory({
      bindDismissible: bindDismissibleFn,
      bindMobileSheet: bindMobileSheetFn,
      closeProjectEntityEditor: _closeProjectEntityEditor,
      closeProjectPackageManifest: _closeProjectPackageManifest,
      closeProjectPackageWizard: _closeProjectPackageWizard,
      closeProjectTargetEditor: _closeProjectTargetEditor,
      closeProjectWorkspace,
      isProjectEntityEditorOpen,
      isProjectPackageManifestOpen,
      isProjectPackageWizardOpen,
      isProjectTargetEditorOpen,
      projectDetailsController: _projectDetailsController,
      projectEntityEditorController: _projectEntityEditorController,
      projectEntityEditorOverlay,
      projectMobileTabs,
      projectPackageManifestOverlay,
      projectPackageWizardOverlay,
      projectPackagesController: _projectPackagesController,
      projectTargetEditorOverlay,
      projectTargetsController: _projectTargetsController,
      projectWorkspaceEventsController: _projectWorkspaceEventsController,
      projectWorkspaceOverlay,
      projectWorkspaceShellController: _projectWorkspaceShellController,
      syncProjectMobileTabEdges: _syncProjectMobileTabEdges,
    });
    return projectWorkspaceBootstrapController;
  }

  let projectTargetsController = null;

  function _projectTargetsController() {
    if (projectTargetsController) return projectTargetsController;
    const factory = global.DarklabProjectTargets && global.DarklabProjectTargets.createProjectTargetsController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectTargets is unavailable');
    projectTargetsController = factory({
      EntityMetadataClient,
      targetHelpers: PROJECT_TARGET_HELPERS,
      overlay: projectTargetEditorOverlay,
      form: projectTargetCreateForm,
      typeSelect: projectTargetTypeSelect,
      valueInput: projectTargetValueInput,
      valueHelp: projectTargetValueHelp,
      valueError: projectTargetValueError,
      labelInput: projectTargetLabelInput,
      notesInput: projectTargetNotesInput,
      title: projectTargetEditorTitle,
      submitButton: projectTargetSubmitButton,
      getLastTargetType: () => projectWorkspaceLastTargetType,
      setLastTargetType: (targetType) => { projectWorkspaceLastTargetType = String(targetType || projectWorkspaceLastTargetType || 'domain'); },
      setEditingTargetId: (targetId) => { projectWorkspaceEditingTargetId = String(targetId || ''); },
      selectedProjectId: () => projectWorkspaceSelectedId,
      activeProject: _activeProject,
      entityLabelValues: _entityLabelValues,
      entityNoteBody: _entityNoteBody,
      entityMetadataChips: _entityMetadataChips,
      entityMetadataChipClass: _entityMetadataChipClass,
      makeProjectButton: _makeProjectButton,
      emptyProjectPanel: _emptyProjectPanel,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      syncEntityLabels: _syncEntityLabels,
      syncEntityNote: _syncEntityNote,
      refreshProjectWorkspace,
      loadProjectAutocompleteTargets: () => {
        if (typeof loadProjectAutocompleteTargets === 'function') {
          loadProjectAutocompleteTargets().catch(() => {});
        }
      },
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      syncProjectWorkspaceNestedSuppression: _syncProjectWorkspaceNestedSuppression,
      installProjectMobileKeyboardGuards: _installProjectMobileKeyboardGuards,
      focusProjectNestedSheet: _focusProjectNestedSheet,
    });
    return projectTargetsController;
  }

  let projectRunsController = null;

  function _projectRunsController() {
    if (projectRunsController) return projectRunsController;
    const factory = global.DarklabProjectRuns && global.DarklabProjectRuns.createProjectRunsController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectRuns is unavailable');
    projectRunsController = factory({
      projectExplorerBody: () => projectExplorerBody,
      projectRunItems: _projectRunItems,
      projectComparableRuns: _projectComparableRuns,
      projectFindingItems: _projectFindingItems,
      projectFindingsLoaded: _projectFindingsLoaded,
      projectArtifactItems: _projectArtifactItems,
      projectArtifactsVisible: _projectArtifactsVisible,
      projectTargetFilterActive: _projectTargetFilterActive,
      filteredProjectRuns: _filteredProjectRuns,
      entityLabelValues: _entityLabelValues,
      entityMetadataChips: _entityMetadataChips,
      formatDate: _formatProjectDate,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      projectItemRow: _projectItemRow,
    });
    return projectRunsController;
  }

  let projectMobileCompareController = null;

  function _projectMobileCompareController() {
    if (projectMobileCompareController) return projectMobileCompareController;
    const factory = global.DarklabProjectMobileCompare && global.DarklabProjectMobileCompare.createProjectMobileCompareController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectMobileCompare is unavailable');
    projectMobileCompareController = factory({
      projectWorkspaceModal,
      projectSummary: (projectId) => projectWorkspaceSummaries.get(String(projectId || '')),
      projectComparableRuns: _projectComparableRuns,
      projectRunBaselineLabelOptions: _projectRunBaselineLabelOptions,
      projectRunCompareOptionText: _projectRunCompareOptionText,
      entityLabelValues: _entityLabelValues,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      compareProjectRuns: _compareProjectRuns,
      closeProjectWorkspace,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
    });
    return projectMobileCompareController;
  }

  let projectMobileShellController = null;

  function _projectMobileShellController() {
    if (projectMobileShellController) return projectMobileShellController;
    const factory = global.DarklabProjectMobileShell && global.DarklabProjectMobileShell.createProjectMobileShellController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectMobileShell is unavailable');
    projectMobileShellController = factory({
      activeProject: _activeProject,
      closeProjectEntityEditor: _closeProjectEntityEditor,
      closeProjectTargetEditor: _closeProjectTargetEditor,
      emptyProjectPanel: _emptyProjectPanel,
      mobileSection: _projectMobileSection,
      orderedProjectRows: _orderedProjectRows,
      projectIsArchived: _projectIsArchived,
      projectMobileBody,
      projectMobileCreateForm,
      projectMobileDetailView,
      projectMobileListView,
      projectMobileNameInput,
      projectMobileRoot,
      projectMobileSummary,
      projectRows: () => projectWorkspaceRows,
      projectWorkspaceLoading: () => projectWorkspaceLoading,
      renderMobileListRow: _renderProjectMobileListRow,
      renderProjectMobileDetail: _renderProjectMobileDetail,
      renderProjectWorkspace: _renderProjectWorkspace,
      selectedProjectId: () => projectWorkspaceSelectedId,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      setSelectedProjectId: (projectId) => { projectWorkspaceSelectedId = String(projectId || ''); },
      setWorkspaceTab: (tabId) => { projectWorkspaceTab = tabId; },
    });
    return projectMobileShellController;
  }

  let projectMobileDetailController = null;

  function _projectMobileDetailController() {
    if (projectMobileDetailController) return projectMobileDetailController;
    const factory = global.DarklabProjectMobileDetail && global.DarklabProjectMobileDetail.createProjectMobileDetailController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectMobileDetail is unavailable');
    projectMobileDetailController = factory({
      projectWorkspaceModal,
      projectMobileDetailView,
      projectMobileDetailBody,
      projectMobileTabs,
      notePreviewLimit: PROJECT_WORKSPACE_CONSTANTS.mobileNotePreviewLimit,
      selectedProjectId: () => projectWorkspaceSelectedId,
      setSelectedProjectId: (projectId) => { projectWorkspaceSelectedId = String(projectId || ''); },
      projectWorkspaceTab: () => projectWorkspaceTab,
      projectWorkspaceLoading: () => projectWorkspaceLoading,
      activeProject: _activeProject,
      projectRows: () => projectWorkspaceRows,
      projectSummary: _projectSummary,
      projectCounts: _projectCounts,
      projectDisplayName: _projectDisplayName,
      projectTargetItems: _projectTargetItems,
      projectRunItems: _projectRunItems,
      projectRunById: _projectRunById,
      projectComparableRuns: _projectComparableRuns,
      projectArtifactItems: _projectArtifactItems,
      projectFindingItems: _projectFindingItems,
      projectFindingsLoaded: _projectFindingsLoaded,
      projectFindingsLoadingId: () => _projectFindingsDataController().loadingId(),
      hasProjectFindings: (projectId) => _projectFindingsDataController().loaded(projectId),
      projectFindingServerFiltersActive: _projectFindingServerFiltersActive,
      projectFindingGroupCollapsed: _projectFindingGroupCollapsed,
      projectArtifactGroupCollapsed: _projectArtifactGroupCollapsed,
      projectTargetFilterActive: _projectTargetFilterActive,
      projectArtifactsVisible: _projectArtifactsVisible,
      projectArtifactStatus: _projectArtifactStatus,
      projectArtifactStatusLabel: _projectArtifactStatusLabel,
      projectArtifactDetailLines: _projectArtifactDetailLines,
      projectFindingTargetText: _projectFindingTargetText,
      projectTargetLabel: _projectTargetLabel,
      projectRunFindingCount: _projectRunFindingCount,
      projectRunArtifactCount: _projectRunArtifactCount,
      filteredProjectRuns: _filteredProjectRuns,
      filteredProjectFindings: _filteredProjectFindings,
      filteredProjectArtifacts: _filteredProjectArtifacts,
      entityLabelValues: _entityLabelValues,
      entityNoteBody: _entityNoteBody,
      entityMetadataChips: _entityMetadataChips,
      entityMetadataChipClass: _entityMetadataChipClass,
      formatDate: _formatProjectDate,
      shortProjectRunId: _shortProjectRunId,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      findingReviewControl: _findingReviewControl,
      renderProjectMobileDetailTopbar: _renderProjectMobileDetailTopbar,
      renderProjectMobileTabs: _renderProjectMobileTabs,
      renderProjectMobileEntitiesTab: (projectId, summary) => _projectEntitiesController().renderMobileEntitiesTab(projectId, summary),
      renderProjectMobilePackagesTab: (projectId, summary) => _projectPackagesController().renderMobilePackagesTab(projectId, summary),
      setProjectMobileView: _setProjectMobileView,
      loadProjectFindings: _loadProjectFindings,
      loadProjectFilteredFindings: _loadProjectFilteredFindings,
      groupBy: _groupBy,
      mobileMenuText: '☰',
      caretText: '▾',
      metaSeparator: ' · ',
    });
    return projectMobileDetailController;
  }

  let projectEntityEditorController = null;

  function _projectEntityEditorController() {
    if (projectEntityEditorController) return projectEntityEditorController;
    const factory = global.DarklabProjectEntityEditor && global.DarklabProjectEntityEditor.createProjectEntityEditorController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectEntityEditor is unavailable');
    projectEntityEditorController = factory({
      overlay: projectEntityEditorOverlay,
      title: projectEntityEditorTitle,
      subtitle: projectEntityEditorSubtitle,
      form: projectEntityEditorForm,
      labelsInput: projectEntityLabelsInput,
      noteInput: projectEntityNoteInput,
      submitButton: projectEntitySubmitButton,
      parseLabelInput: EntityMetadataClient.parseLabelInput,
      entityTitleForEditor: _entityTitleForEditor,
      entityEditorLabelForType: _entityEditorLabelForType,
      entityLabelValues: _entityLabelValues,
      entityNoteBody: _entityNoteBody,
      syncEntityLabels: _syncEntityLabels,
      syncEntityNote: _syncEntityNote,
      refreshProjectWorkspace,
      invalidateProjectFindings: _invalidateProjectFindings,
      loadProjectFindings: _loadProjectFindings,
      renderProjectExplorer: _renderProjectExplorer,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      syncProjectWorkspaceNestedSuppression: _syncProjectWorkspaceNestedSuppression,
      installProjectMobileKeyboardGuards: _installProjectMobileKeyboardGuards,
      focusProjectNestedSheet: _focusProjectNestedSheet,
    });
    return projectEntityEditorController;
  }

  let projectWorkspaceLifecycleController = null;

  function _projectWorkspaceLifecycleController() {
    if (projectWorkspaceLifecycleController) return projectWorkspaceLifecycleController;
    const factory = global.DarklabProjectWorkspaceLifecycle
      && global.DarklabProjectWorkspaceLifecycle.createProjectWorkspaceLifecycleController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectWorkspaceLifecycle is unavailable');
    projectWorkspaceLifecycleController = factory({
      apiFetch,
      projectWorkspaceBody,
      selectedProjectId: () => projectWorkspaceSelectedId,
      setSelectedProjectId: (projectId) => { projectWorkspaceSelectedId = String(projectId || ''); },
      projectRows: () => projectWorkspaceRows,
      setProjectRows: (rows) => { projectWorkspaceRows = Array.isArray(rows) ? rows : []; },
      projectSummaries: () => projectWorkspaceSummaries,
      setProjectSummaries: (summaries) => { projectWorkspaceSummaries = summaries instanceof Map ? summaries : new Map(); },
      projectWorkspaceLoading: () => projectWorkspaceLoading,
      setProjectWorkspaceLoading: (loading) => { projectWorkspaceLoading = !!loading; },
      activeProject: _activeProject,
      loadActiveProjectContext,
      invalidateProjectFindings: _invalidateProjectFindings,
      renderProjectWorkspace: _renderProjectWorkspace,
      syncProjectNotesForm: _syncProjectNotesForm,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      logClientError: (message, err) => {
        if (typeof logClientError === 'function') logClientError(message, err);
      },
    });
    return projectWorkspaceLifecycleController;
  }

  let projectWorkspaceEventsController = null;

  function _projectWorkspaceEventsController() {
    if (projectWorkspaceEventsController) return projectWorkspaceEventsController;
    const factory = global.DarklabProjectWorkspaceEvents
      && global.DarklabProjectWorkspaceEvents.createProjectWorkspaceEventsController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectWorkspaceEvents is unavailable');
    projectWorkspaceEventsController = factory({
      activeProject: _activeProject,
      artifactGroupKey: _projectArtifactGroupKey,
      avoidProjectRunCompareLabelSelfTarget: _avoidProjectRunCompareLabelSelfTarget,
      clearEditingTargetIf: (targetId) => {
        if (projectWorkspaceEditingTargetId === String(targetId || '')) projectWorkspaceEditingTargetId = '';
      },
      closeProjectEntityEditor: _closeProjectEntityEditor,
      closeProjectFilterMenus: _closeProjectFilterMenus,
      closeProjectPackageManifest: _closeProjectPackageManifest,
      closeProjectTargetEditor: _closeProjectTargetEditor,
      closeProjectWorkspace,
      compareProjectRuns: _compareProjectRuns,
      confirmProjectDelete: _confirmProjectDelete,
      confirmProjectDestructive: _confirmProjectDestructive,
      confirmProjectPackageDelete: _confirmProjectPackageDelete,
      confirmProjectRunUnlink: _confirmProjectRunUnlink,
      confirmProjectTargetDelete: _confirmProjectTargetDelete,
      downloadProjectArtifact: _downloadProjectArtifact,
      downloadProjectPackage: _downloadProjectPackage,
      entitiesController: _projectEntitiesController,
      entitySelectMode: () => projectWorkspaceEntitySelectMode,
      filteredProjectFindings: _filteredProjectFindings,
      filtersController: _projectFiltersController,
      findingGroupKey: _projectFindingGroupKey,
      findingSelectMode: () => projectWorkspaceFindingSelectMode,
      flushProjectNotesAutosave: _flushProjectNotesAutosave,
      invalidateProjectFindings: _invalidateProjectFindings,
      isProjectWorkspaceOpen,
      linkLastRunToProject: _linkLastRunToProject,
      loadProjectAutocompleteTargets: () => {
        if (typeof loadProjectAutocompleteTargets === 'function') {
          loadProjectAutocompleteTargets().catch(() => {});
        }
      },
      loadProjectFindings: _loadProjectFindings,
      mobileView: () => _projectMobileShellController().currentView(),
      openProjectEntityEditor: _openProjectEntityEditor,
      openProjectEntityInAtlas: _openProjectEntityInAtlas,
      openProjectEntityPicker: _openProjectEntityPicker,
      openProjectMobileActionSheet: _openProjectMobileActionSheet,
      openProjectMobileCompareSheet: _openProjectMobileCompareSheet,
      openProjectPackageManifest: _openProjectPackageManifest,
      openProjectPackageWizardFromPackage: _openProjectPackageWizardFromPackage,
      openProjectTargetEditor: _openProjectTargetEditor,
      packagesController: _projectPackagesController,
      previewProjectArtifact: _previewProjectArtifact,
      projectArtifactItems: _projectArtifactItems,
      projectDisplayName: _projectDisplayName,
      projectExplorerBody,
      projectFindingItems: _projectFindingItems,
      projectFindingLabelFilterSet: _projectFindingLabelFilterSet,
      projectFindingStatusFilterSet: _projectFindingStatusFilterSet,
      projectMobileDetailBody,
      projectMobileListView,
      projectMobileProjectActions: _projectMobileProjectActions,
      projectPackageById: _projectPackageById,
      projectRows: () => projectWorkspaceRows,
      projectRunFilterSet: _projectRunFilterSet,
      projectRunItems: _projectRunItems,
      projectSummary: _projectSummary,
      projectTargetFilterSet: _projectTargetFilterSet,
      projectTargetItems: _projectTargetItems,
      projectWorkspaceModal,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      refreshProjectWorkspace,
      renderProjectExplorer: _renderProjectExplorer,
      renderProjectMobile: _renderProjectMobile,
      renderProjectMobileDetail: _renderProjectMobileDetail,
      renderProjectWorkspace: _renderProjectWorkspace,
      selectedEntityIds: () => projectWorkspaceSelectedEntityIds,
      selectedFindingIds: () => projectWorkspaceSelectedFindingIds,
      selectedProjectId: () => projectWorkspaceSelectedId,
      selectProjectFromMobile: _selectProjectFromMobile,
      setCachedFindingReviewState: _setCachedFindingReviewState,
      setFindingSelectMode: (enabled) => { projectWorkspaceFindingSelectMode = !!enabled; },
      setProjectMobileCreateOpen: _setProjectMobileCreateOpen,
      setProjectMobileView: _setProjectMobileView,
      setProjectPackageDownloadBusy: _setProjectPackageDownloadBusy,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      setProjectRunCompareMode: _setProjectRunCompareMode,
      setSelectedProjectId: (projectId) => { projectWorkspaceSelectedId = String(projectId || ''); },
      setWorkspaceTab: (tabId) => { projectWorkspaceTab = tabId; },
      syncProjectRunCompareMode: _syncProjectRunCompareMode,
      toggleArtifactGroup: (projectId, runId) => {
        const key = _projectArtifactGroupKey(projectId, runId);
        if (projectWorkspaceCollapsedArtifactGroups.has(key)) projectWorkspaceCollapsedArtifactGroups.delete(key);
        else projectWorkspaceCollapsedArtifactGroups.add(key);
      },
      toggleFindingGroup: (projectId, runLabel) => {
        const key = _projectFindingGroupKey(projectId, runLabel);
        if (projectWorkspaceCollapsedFindingGroups.has(key)) projectWorkspaceCollapsedFindingGroups.delete(key);
        else projectWorkspaceCollapsedFindingGroups.add(key);
      },
      toggleMobileArchivedOpen: () => {
        _projectMobileShellController().setArchivedOpen(!_projectMobileShellController().isArchivedOpen());
      },
      workspaceTab: () => projectWorkspaceTab,
    });
    return projectWorkspaceEventsController;
  }

  function _projectTargetById(summary, targetId) {
    return _projectFiltersController().targetById(summary, targetId);
  }

  function _projectTargetFilterLabel(target) {
    return _projectFiltersController().targetFilterLabel(target);
  }

  function _targetFilterableProjectTab() {
    return _projectFiltersController().targetFilterableProjectTab(projectWorkspaceTab);
  }

  function _projectTargetFilterSet(projectId = projectWorkspaceSelectedId) {
    return _projectFiltersController().targetFilterSet(projectId);
  }

  function _projectTargetFilterIds(projectId = projectWorkspaceSelectedId, summary = _projectSummary(projectId)) {
    return _projectFiltersController().targetFilterIds(projectId, summary);
  }

  function _projectTargetFilterActive(projectId = projectWorkspaceSelectedId, summary = _projectSummary(projectId)) {
    return _projectFiltersController().targetFilterActive(projectId, summary);
  }

  function _projectRunFilterSet(projectId = projectWorkspaceSelectedId) {
    return _projectFiltersController().runFilterSet(projectId);
  }

  function _projectRunFilterIds(projectId = projectWorkspaceSelectedId, summary = _projectSummary(projectId)) {
    return _projectFiltersController().runFilterIds(projectId, summary);
  }

  function _projectRunFilterActive(projectId = projectWorkspaceSelectedId, summary = _projectSummary(projectId)) {
    return _projectFiltersController().runFilterActive(projectId, summary);
  }

  function _projectRunFilterLabel(run) {
    return _projectFiltersController().runFilterLabel(run);
  }

  function _projectRunFilterChipLabel(run) {
    return _projectFiltersController().runFilterChipLabel(run);
  }

  function _projectFindingStatusFilterSet(projectId = projectWorkspaceSelectedId) {
    return _projectFiltersController().findingStatusFilterSet(projectId);
  }

  function _projectFindingStatusFilterValues(projectId = projectWorkspaceSelectedId) {
    return _projectFiltersController().findingStatusFilterValues(projectId);
  }

  function _projectFindingStatusFilterActive(projectId = projectWorkspaceSelectedId) {
    return _projectFiltersController().findingStatusFilterActive(projectId);
  }

  function _projectFindingLabelFilterSet(projectId = projectWorkspaceSelectedId) {
    return _projectFiltersController().findingLabelFilterSet(projectId);
  }

  function _projectFindingLabelOptions(projectId = projectWorkspaceSelectedId) {
    return _projectFiltersController().findingLabelOptions(projectId);
  }

  function _projectFindingLabelFilterValues(projectId = projectWorkspaceSelectedId) {
    return _projectFiltersController().findingLabelFilterValues(projectId);
  }

  function _projectFindingLabelFilterActive(projectId = projectWorkspaceSelectedId) {
    return _projectFiltersController().findingLabelFilterActive(projectId);
  }

  function _projectFindingNoteStateValue(projectId = projectWorkspaceSelectedId) {
    return _projectFiltersController().findingNoteStateValue(projectId);
  }

  function _projectFindingNoteStateFilterActive(projectId = projectWorkspaceSelectedId) {
    return _projectFiltersController().findingNoteStateFilterActive(projectId);
  }

  function _projectFindingOrphanFilterValue(projectId = projectWorkspaceSelectedId) {
    return _projectFiltersController().findingOrphanFilterValue(projectId);
  }

  function _projectFindingOrphanFilterActive(projectId = projectWorkspaceSelectedId) {
    return _projectFiltersController().findingOrphanFilterActive(projectId);
  }

  function _projectFindingSortValue(projectId = projectWorkspaceSelectedId) {
    return _projectFiltersController().findingSortValue(projectId);
  }

  function _projectFindingTargetText(summary, finding) {
    return _projectFiltersController().findingTargetText(summary, finding);
  }

  function _sortProjectFindings(findings, projectId, summary) {
    return _projectFiltersController().sortProjectFindings(findings, projectId, summary);
  }

  function _findingReviewStateLabel(value) {
    return _projectFindingsController().reviewStateLabel(value);
  }

  function _projectFindingGroupKey(projectId, runLabel) {
    return _projectFindingsController().groupKey(projectId, runLabel);
  }

  function _projectFindingGroupCollapsed(projectId, runLabel) {
    return _projectFindingsController().groupCollapsed(projectId, runLabel);
  }

  function _projectArtifactGroupKey(projectId, runId) {
    return _projectArtifactsController().groupKey(projectId, runId);
  }

  function _projectArtifactGroupCollapsed(projectId, runId) {
    return _projectArtifactsController().groupCollapsed(projectId, runId);
  }

  function _projectRunItems(summary) {
    return _projectSharedUiController().runItems(summary);
  }

  function _projectRunById(summary, runId) {
    return _projectSharedUiController().runById(summary, runId);
  }

  function _projectComparableRuns(summary) {
    return _projectSharedUiController().comparableRuns(summary);
  }

  function _shortProjectRunId(runId) {
    return _projectSharedUiController().shortRunId(runId);
  }

  function _projectArtifactItems(summary) {
    return _projectArtifactsController().items(summary);
  }

  function _projectFilesEnabled() {
    return _projectArtifactsController().filesEnabled();
  }

  function _projectArtifactsVisible() {
    return _projectArtifactsController().artifactsVisible();
  }

  function _projectArtifactStatus(artifact) {
    return _projectArtifactsController().status(artifact);
  }

  function _projectArtifactStatusLabel(artifact) {
    return _projectArtifactsController().statusLabel(artifact);
  }

  function _projectArtifactAccessory(projectId, artifact) {
    return _projectArtifactsController().accessory(projectId, artifact);
  }

  function _entityLabelValues(entity) {
    return _projectSharedUiController().entityLabelValues(entity);
  }

  function _entityNoteBody(entity) {
    return _projectSharedUiController().entityNoteBody(entity);
  }

  function _entityMetadataChips(entity) {
    return _projectSharedUiController().entityMetadataChips(entity);
  }

  function _entityMetadataChipClass(kind = 'label') {
    return _projectSharedUiController().entityMetadataChipClass(kind);
  }

  function _appendProjectLabelChips(parent, project, { className = 'project-label-chips' } = {}) {
    _projectDetailsController().appendLabelChips(parent, project, { className });
  }

  function _appendProjectMobileLabelChips(parent, project) {
    _projectDetailsController().appendMobileLabelChips(parent, project);
  }

  function _entityTitleForEditor(entityType, entity) {
    return _projectSharedUiController().entityTitleForEditor(entityType, entity);
  }

  function _entityEditorLabelForType(entityType) {
    return _projectSharedUiController().entityEditorLabelForType(entityType);
  }

  function _projectArtifactDetail(artifact) {
    return _projectArtifactsController().detail(artifact);
  }

  function _projectArtifactDetailLines(artifact) {
    return _projectArtifactsController().detailLines(artifact);
  }

  function _projectArtifactDownloadName(artifactPath = '', fallback = 'artifact') {
    return _projectArtifactsController().downloadName(artifactPath, fallback);
  }

  function _downloadBlobAsAttachment(blob, filename, successMessage = '') {
    _projectSharedUiController().downloadBlobAsAttachment(blob, filename, successMessage);
  }

  function _syncProjectWorkspaceNestedSuppression() {
    _projectNestedSheetsController().syncWorkspaceSuppression();
  }

  function _focusProjectNestedSheet(overlay, preferred = null) {
    _projectNestedSheetsController().focusNestedSheet(overlay, preferred);
  }

  function _syncProjectMobileFocusedField() {
    _projectNestedSheetsController().syncMobileFocusedField();
  }

  function _installProjectMobileKeyboardGuards() {
    _projectNestedSheetsController().installKeyboardGuards();
  }

  function _closeProjectPackageManifest() {
    _projectPackagesController().closeManifest();
  }

  function isProjectPackageManifestOpen() {
    return _projectPackagesController().isManifestOpen();
  }

  function _openProjectPackageManifest(pkg) {
    _projectPackagesController().openManifest(pkg);
  }

  async function _previewProjectArtifact(projectId, artifactId) {
    await _projectArtifactsController().preview(projectId, artifactId);
  }

  async function _downloadProjectArtifact(projectId, artifactId, artifactPath = '') {
    await _projectArtifactsController().download(projectId, artifactId, artifactPath);
  }

  function _projectPackageItems(summary) {
    return _projectPackagesController().items(summary);
  }

  function _projectPackageWizardActive(projectId = projectWorkspaceSelectedId) {
    return _projectPackagesController().isWizardActive(projectId);
  }

  function isProjectPackageWizardOpen() {
    return _projectPackagesController().isWizardOpen();
  }

  function isProjectEntityEditorOpen() {
    return _projectEntityEditorController().isOpen();
  }

  function _closeProjectEntityEditor() {
    _projectEntityEditorController().close();
  }

  function _openProjectEntityEditor(projectId, entityType, entity, options = {}) {
    _projectEntityEditorController().open(projectId, entityType, entity, options);
  }

  global.openEntityMetadataEditor = function openEntityMetadataEditor(entityType, entity, options = {}) {
    const projectId = options && Object.prototype.hasOwnProperty.call(options, 'projectId')
      ? options.projectId
      : '';
    _openProjectEntityEditor(projectId, entityType, entity, options);
  };

  function _renderProjectPackageWizardModal(options = {}) {
    _projectPackagesController().renderWizardModal(options);
  }

  function _openProjectPackageWizard(projectId, preset = 'evidence') {
    _projectPackagesController().openWizard(projectId, preset);
  }

  function _openProjectPackageWizardFromPackage(projectId, pkg) {
    _projectPackagesController().openWizardFromPackage(projectId, pkg);
  }

  function _closeProjectPackageWizard(options = {}) {
    _projectPackagesController().closeWizard(options);
  }

  function _projectPackageById(summary, packageId) {
    return _projectPackagesController().byId(summary, packageId);
  }

  function _setProjectPackageDownloadBusy(button, busy) {
    _projectPackagesController().setDownloadBusy(button, busy);
  }

  async function _downloadProjectPackage(projectId, pkg) {
    await _projectPackagesController().downloadPackage(projectId, pkg);
  }

  function _projectFindingItems(projectId = projectWorkspaceSelectedId) {
    return _projectFindingsDataController().items(projectId);
  }

  function _projectFindingsLoaded(projectId = projectWorkspaceSelectedId) {
    return _projectFindingsDataController().loaded(projectId);
  }

  function _projectFindingServerFilterParams(projectId, summary = _projectSummary(projectId)) {
    return _projectFiltersController().findingServerFilterParams(projectId, summary);
  }

  function _projectFindingServerFiltersActive(projectId = projectWorkspaceSelectedId, summary = _projectSummary(projectId)) {
    return _projectFiltersController().findingServerFiltersActive(projectId, summary);
  }

  function _projectFindingFilteredKey(projectId = projectWorkspaceSelectedId, summary = _projectSummary(projectId)) {
    return _projectFiltersController().findingFilteredKey(projectId, summary);
  }

  function _projectFilteredFindingItems(projectId = projectWorkspaceSelectedId, summary = _projectSummary(projectId)) {
    return _projectFiltersController().filteredFindingItems(projectId, summary);
  }

  function _invalidateProjectFilteredFindings(projectId = '') {
    _projectFindingsDataController().invalidateFiltered(projectId);
  }

  function _invalidateProjectFindings(projectId = '') {
    _projectFindingsDataController().invalidate(projectId);
  }

  function _projectTargetLabel(summary, targetId) {
    return _projectSharedUiController().targetLabel(summary, targetId);
  }

  function _formatProjectDate(value) {
    return _projectSharedUiController().formatDate(value);
  }

  function _formatProjectBytes(value) {
    return _projectSharedUiController().formatBytes(value);
  }

  function _emptyProjectPanel(text) {
    return _projectSharedUiController().emptyPanel(text);
  }

  function _projectMetaRow(label, value) {
    return _projectSharedUiController().metaRow(label, value);
  }

  function _projectItemRow({ title, meta = '', detail = '', badge = '', chips = [], action = null, accessory = null, forceArticle = false }) {
    return _projectSharedUiController().itemRow({ title, meta, detail, badge, chips, action, accessory, forceArticle });
  }

  function _findingReviewControl(finding, projectId) {
    return _projectFindingsController().reviewControl(finding, projectId);
  }

  function _findingRowAccessory(finding, projectId) {
    return _projectFindingsController().rowAccessory(finding, projectId);
  }

  function _openProjectTargetEditor(projectId, target = null) {
    _projectTargetsController().openEditor(projectId, target);
  }

  function _closeProjectTargetEditor(options = {}) {
    _projectTargetsController().closeEditor(options);
  }

  function isProjectTargetEditorOpen() {
    return _projectTargetsController().isOpen();
  }

  function _projectTargetDisplayRow(projectId, target) {
    return _projectTargetsController().targetDisplayRow(projectId, target);
  }

  function _projectRunRemoveControl(projectId, run) {
    return _projectRunsController().runRemoveControl(projectId, run);
  }

  function _projectRunFindingCount(projectId, runId) {
    return _projectRunsController().runFindingCount(projectId, runId);
  }

  function _projectRunArtifactCount(summary, runId) {
    return _projectRunsController().runArtifactCount(summary, runId);
  }

  function _projectRunControls(projectId, run, summary) {
    return _projectRunsController().runControls(projectId, run, summary);
  }

  function _projectRunBaselineLabelOptions(runs) {
    return _projectRunsController().baselineLabelOptions(runs);
  }

  function _projectRunCompareOptionText(run) {
    return _projectRunsController().compareOptionText(run);
  }

  function _syncProjectRunCompareMode(wrap) {
    _projectRunsController().syncCompareMode(wrap);
  }

  function _setProjectRunCompareMode(modeButton, event = null) {
    _projectRunsController().setCompareMode(modeButton, event);
  }

  function _avoidProjectRunCompareLabelSelfTarget(container, label) {
    _projectRunsController().avoidCompareLabelSelfTarget(container, label);
  }

  function _compareProjectRuns(projectId, leftId, mode, targetValue, controls = null) {
    _projectRunsController().compareRuns(projectId, leftId, mode, targetValue, controls);
  }

  function _renderProjectRunCompareControls(runs) {
    return _projectRunsController().renderCompareControls(runs);
  }

  function _renderProjectTargets(projectId, targets) {
    return _projectTargetsController().renderTargets(projectId, targets);
  }

  function _setProjectFilterMenuOpen(menu, open) {
    _projectFiltersController().setFilterMenuOpen(menu, open);
  }

  function _closeProjectFilterMenus(exceptMenu = null) {
    _projectFiltersController().closeFilterMenus(exceptMenu);
  }

  function _renderProjectFilterBar(projectId, summary) {
    return _projectFiltersController().renderFilterBar(projectId, summary);
  }

  function _syncProjectFilterSortDivider(root) {
    _projectFiltersController().syncFilterSortDivider(root);
  }

  function _scheduleProjectFilterSortDividerSync(root) {
    _projectFiltersController().scheduleFilterSortDividerSync(root);
  }

  function _projectRunDirectTargetIds(run) {
    return _projectFiltersController().runDirectTargetIds(run);
  }

  function _projectFindingTargetIds(finding) {
    return _projectFiltersController().findingTargetIds(finding);
  }

  function _projectRunIdsMatchingTargets(projectId, filterIds) {
    return _projectFiltersController().runIdsMatchingTargets(projectId, filterIds);
  }

  function _projectRunMatchesTargetFilters(run, projectId, filterIds, matchingRunIds) {
    return _projectFiltersController().runMatchesTargetFilters(run, projectId, filterIds, matchingRunIds);
  }

  function _filteredProjectRuns(projectId, summary) {
    return _projectFiltersController().filteredRuns(projectId, summary);
  }

  function _filteredProjectFindings(projectId, summary) {
    return _projectFiltersController().filteredFindings(projectId, summary);
  }

  function _filteredProjectArtifacts(projectId, summary) {
    return _projectFiltersController().filteredArtifacts(projectId, summary);
  }

  function _groupBy(items, keyFn) {
    return _projectSharedUiController().groupBy(items, keyFn);
  }

  async function _loadProjectFindings(projectId) {
    return _projectFindingsDataController().load(projectId);
  }

  async function _loadProjectFilteredFindings(projectId, summary = _projectSummary(projectId)) {
    await _projectFindingsDataController().loadFiltered(projectId, summary);
  }

  function _syncProjectForms(project = _selectedProject()) {
    _projectDetailsController().syncForms(project);
  }

  function _syncProjectNotesForm() {
    _projectDetailsController().syncNotesForm();
  }

  function _flushProjectNotesAutosave() {
    return _projectDetailsController().flushNotesAutosave();
  }

  function _makeProjectButton(label, action, projectId, role = 'secondary', tone = '') {
    return _projectSharedUiController().makeButton(label, action, projectId, role, tone);
  }

  function _projectIsArchived(project) {
    return _projectListController().isArchived(project);
  }

  function _orderedProjectRows(activeId, rows = projectWorkspaceRows) {
    return _projectListController().orderedRows(activeId, rows);
  }

  function _renderProjectList() {
    _projectListController().renderList();
  }

  function _projectMobileTabItems(projectId, summary) {
    return _projectNavigationController().mobileTabItems(projectId, summary);
  }

  const _PROJECT_MOBILE_TAB_EDGE_OPTS = { wrapSelector: '.project-mobile-tabs-wrap' };

  function _syncProjectMobileActiveTabScroll() {
    if (typeof window.syncActiveTabStripScroll === 'function') {
      window.syncActiveTabStripScroll(projectMobileTabs, _PROJECT_MOBILE_TAB_EDGE_OPTS);
    }
  }

  function _syncProjectMobileTabEdges() {
    if (typeof window.syncTabStripEdges === 'function') {
      window.syncTabStripEdges(projectMobileTabs, _PROJECT_MOBILE_TAB_EDGE_OPTS);
    }
  }

  function _renderProjectMobileListRow(project, activeId) {
    return _projectListController().renderMobileListRow(project, activeId);
  }

  function _projectMobileSection(label, count, { open = true } = {}) {
    return _projectListController().mobileSection(label, count, { open });
  }

  function _setProjectMobileCreateOpen(open, { focus = false } = {}) {
    _projectMobileShellController().setCreateOpen(open, { focus });
  }

  function _setProjectMobileView(view) {
    _projectMobileShellController().setView(view);
  }

  function _selectProjectFromMobile(projectId, tab = '') {
    _projectMobileShellController().selectProject(projectId, tab);
  }

  function _projectMobileProjectActions(project) {
    return _projectMobileShellController().projectActions(project);
  }

  function _renderProjectMobileDetailTopbar(project, activeId) {
    _projectNavigationController().renderMobileDetailTopbar(project, activeId);
  }

  function _renderProjectMobileTabs(projectId, summary) {
    _projectNavigationController().renderMobileTabs(projectId, summary);
  }

  function _projectMobileActionMenu(projectId, label, actions = []) {
    return _projectMobileDetailController().actionMenu(projectId, label, actions);
  }

  function _closeProjectMobileActionSheet({ restoreFocus = true } = {}) {
    _projectMobileDetailController().closeActionSheet({ restoreFocus });
  }

  function _openProjectMobileActionSheet(projectId, label, actions = [], returnFocus = null) {
    _projectMobileDetailController().openActionSheet(projectId, label, actions, returnFocus);
  }

  function _closeProjectMobileCompareSheet({ restoreFocus = true } = {}) {
    _projectMobileCompareController().close({ restoreFocus });
  }

  function _openProjectMobileCompareSheet(projectId, returnFocus = null) {
    _projectMobileCompareController().open(projectId, returnFocus);
  }

  function _projectMobileContentRow({
    title,
    meta = '',
    detail = '',
    badge = '',
    chips = [],
    action = null,
    accessory = null,
    className = '',
  }) {
    return _projectMobileDetailController().contentRow({
      title,
      meta,
      detail,
      badge,
      chips,
      action,
      accessory,
      className,
    });
  }

  function _projectMobileEmptyPanel(text, actions = []) {
    return _projectMobileDetailController().emptyPanel(text, actions);
  }

  function _renderProjectMobileDetail() {
    _projectMobileDetailController().renderDetail();
  }

  function _renderProjectMobile() {
    _projectMobileShellController().renderMobile();
  }

  function _renderProjectHeader(project, summary) {
    return _projectNavigationController().renderProjectHeader(project, summary);
  }

  function _focusProjectWorkspaceTab(tabId) {
    _projectNavigationController().focusWorkspaceTab(tabId);
  }

  function cycleProjectWorkspaceTab(offset = 1) {
    return _projectWorkspaceRendererController().cycleTab(offset);
  }

  function _renderProjectDetails(container, project, summary) {
    _projectDetailsController().renderDetails(container, project, summary);
  }

  function _renderProjectRuns(container, projectId, summary) {
    _projectRunsController().renderRuns(container, projectId, summary);
  }

  function _openProjectEntityInAtlas(projectId, summary, entity) {
    _projectEntitiesController().openInAtlas(projectId, summary, entity);
  }

  function _openProjectEntityPicker(projectId) {
    _projectEntitiesController().openPicker(projectId);
  }

  function _renderProjectEntities(container, projectId, summary) {
    _projectEntitiesController().renderEntities(container, projectId, summary);
  }

  function _renderProjectFindings(container, projectId, summary) {
    _projectFindingsController().renderFindings(container, projectId, summary);
  }

  function _renderProjectArtifacts(container, projectId, summary) {
    _projectArtifactsController().renderArtifacts(container, projectId, summary);
  }

  function _renderProjectPackages(container, projectId, summary) {
    _projectPackagesController().renderPackages(container, projectId, summary);
  }

  function _renderProjectExplorer() {
    _projectWorkspaceRendererController().renderExplorer();
  }

  function _renderProjectWorkspace() {
    _projectWorkspaceRendererController().renderWorkspace();
  }

  async function _loadProjectSummaries(projects) {
    await _projectWorkspaceLifecycleController().loadProjectSummaries(projects);
  }

  async function refreshProjectWorkspace() {
    await _projectWorkspaceLifecycleController().refreshProjectWorkspace();
  }

  function _scheduleProjectWorkspaceExternalRefresh() {
    _projectWorkspaceShellController().scheduleExternalRefresh();
  }

  function _notifyProjectWorkspaceChanged(reason = 'updated', projectId = '', { local = true } = {}) {
    _projectWorkspaceShellController().notifyChanged(reason, projectId, { local });
  }

  _projectActiveContextController().bindTargetDiscoveryEvent();

  async function openProjectWorkspace() {
    await _projectWorkspaceShellController().open();
  }

  function closeProjectWorkspace({ refocus = true } = {}) {
    _projectWorkspaceShellController().close({ refocus });
  }

  async function _projectWorkspaceRequest(url, options = {}) {
    return _projectWorkspaceShellController().request(url, options);
  }

  async function _syncEntityLabels(entityType, entityId, nextLabels) {
    await _projectWorkspaceActionsController().syncEntityLabels(entityType, entityId, nextLabels);
  }

  async function _syncEntityNote(entityType, entityId, body) {
    await _projectWorkspaceActionsController().syncEntityNote(entityType, entityId, body);
  }

  async function _linkLastRunToProject(projectId, summary) {
    await _projectWorkspaceActionsController().linkLastRunToProject(projectId, summary);
  }

  async function _confirmProjectDestructive({ body, actionLabel, actionId, note }) {
    return _projectWorkspaceActionsController().confirmDestructive({ body, actionLabel, actionId, note });
  }

  function _confirmProjectTargetDelete(targetValue) {
    return _projectWorkspaceActionsController().confirmTargetDelete(targetValue);
  }

  function _confirmProjectRunUnlink(runCommand) {
    return _projectWorkspaceActionsController().confirmRunUnlink(runCommand);
  }

  function _confirmProjectPackageDelete(packageName) {
    return _projectWorkspaceActionsController().confirmPackageDelete(packageName);
  }

  function _confirmProjectDelete(projectName) {
    return _projectWorkspaceActionsController().confirmProjectDelete(projectName);
  }

  function _setCachedFindingReviewState(projectId, findingId, reviewState) {
    _projectFindingsDataController().setCachedReviewState(projectId, findingId, reviewState);
  }

  _projectWorkspaceBootstrapController().bindAll();

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
    if (e.key === PROJECT_WORKSPACE_CONSTANTS.workspaceBroadcastKey && e.newValue) {
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
  global.getActiveProjectContext = _activeProject;
  global.refreshActiveProjectContext = loadActiveProjectContext;
  global.openProjectWorkspace = openProjectWorkspace;
  global.closeProjectWorkspace = closeProjectWorkspace;
  global.isProjectWorkspaceOpen = isProjectWorkspaceOpen;
  global.cycleProjectWorkspaceTab = cycleProjectWorkspaceTab;
  global.closeProjectTargetEditor = _closeProjectTargetEditor;
  global.isProjectTargetEditorOpen = isProjectTargetEditorOpen;
  global.isProjectPackageManifestOpen = isProjectPackageManifestOpen;
  global.refreshProjectWorkspace = refreshProjectWorkspace;
  global.notifyProjectWorkspaceChanged = _notifyProjectWorkspaceChanged;

})(globalThis);
