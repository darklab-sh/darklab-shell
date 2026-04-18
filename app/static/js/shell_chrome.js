// ── Shell chrome controller ──
// Owns the V07 left sidebar (Recent, Workflows, nav) and the bottom HUD.
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
  const railNav           = document.getElementById('rail-nav');

  const hudStatusCell     = document.getElementById('hud-status-cell');
  const hudRuntimeCell    = document.getElementById('hud-runtime-cell');

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
    workflowsOpen: readBool(PREF_WORKFLOWS, false),
    recentHeight: null, // null → auto-size next time Workflows opens
  };

  let allWorkflows = [];

  // ── Layout application ──────────────────────────────────────────
  function applyCollapsed() {
    rail.classList.toggle('rail-collapsed', ui.collapsed);
    rail.style.setProperty('--rail-w', ui.collapsed ? '44px' : `${ui.railW}px`);
    if (railCollapseBtn) railCollapseBtn.textContent = ui.collapsed ? '»' : '«';
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
  function toggleRecent() {
    ui.recentOpen = !ui.recentOpen;
    applySectionsState();
    writePref(PREF_RECENT, ui.recentOpen ? '1' : '0');
  }
  function toggleWorkflows() {
    const wasOpen = ui.workflowsOpen;
    ui.workflowsOpen = !wasOpen;
    writePref(PREF_WORKFLOWS, ui.workflowsOpen ? '1' : '0');
    if (!ui.workflowsOpen) ui.recentHeight = null; // reset auto-size next open
    applySectionsState();

    if (ui.workflowsOpen && ui.recentOpen && ui.recentHeight == null) {
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

  railRecentHeader?.addEventListener('click', toggleRecent);
  railWorkflowsHeader?.addEventListener('click', toggleWorkflows);

  // ── Recent list rendering ───────────────────────────────────────
  function renderRailRecent() {
    if (!railRecentBody) return;
    const items = Array.isArray(global.cmdHistory) ? global.cmdHistory : [];
    railRecentBody.replaceChildren();
    if (railRecentCount) railRecentCount.textContent = String(items.length);

    if (!items.length) {
      const empty = document.createElement('div');
      empty.className = 'rail-section-empty';
      empty.textContent = 'no commands yet';
      railRecentBody.appendChild(empty);
      return;
    }
    items.forEach(cmd => {
      const row = document.createElement('button');
      row.type = 'button';
      row.className = 'rail-item';
      row.title = cmd;
      const text = document.createElement('span');
      text.className = 'rail-item-text';
      text.textContent = cmd;
      row.appendChild(text);
      row.addEventListener('click', () => {
        if (typeof setComposerValue === 'function') {
          setComposerValue(cmd, cmd.length, cmd.length);
        }
        if (typeof focusAnyComposerInput === 'function') {
          focusAnyComposerInput({ preventScroll: true });
        }
        if (typeof resetCmdHistoryNav === 'function') resetCmdHistoryNav();
      });
      railRecentBody.appendChild(row);
    });
  }

  // Hook into renderHistory() so the sidebar re-syncs whenever the chip row does.
  if (typeof global.renderHistory === 'function') {
    const originalRenderHistory = global.renderHistory;
    global.renderHistory = function wrappedRenderHistory(...args) {
      const result = originalRenderHistory.apply(this, args);
      try { renderRailRecent(); } catch (e) { /* non-critical */ }
      return result;
    };
  }

  // ── Workflows list rendering ────────────────────────────────────
  function renderRailWorkflows(items) {
    allWorkflows = Array.isArray(items) ? items.slice() : [];
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
      row.className = 'rail-item rail-item-muted';
      row.title = wf.description || wf.title || '';
      const glyph = document.createElement('span');
      glyph.textContent = '›';
      glyph.style.flex = '0 0 auto';
      const text = document.createElement('span');
      text.className = 'rail-item-text';
      text.textContent = wf.title || wf.name || `workflow ${idx + 1}`;
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
      renderWorkflowItems([item]);
    }
    if (typeof openWorkflows === 'function') {
      openWorkflows();
    } else if (typeof showWorkflowsOverlay === 'function') {
      showWorkflowsOverlay();
    }
  }

  // When the workflows modal closes, restore the full list so a subsequent
  // open shows everything — covers backdrop click, close button, Escape, and
  // the cross-overlay helpers that call closeWorkflows() directly.
  if (typeof global.closeWorkflows === 'function') {
    const originalClose = global.closeWorkflows;
    global.closeWorkflows = function wrappedCloseWorkflows(...args) {
      const result = originalClose.apply(this, args);
      if (typeof renderWorkflowItems === 'function') {
        try { renderWorkflowItems(allWorkflows); } catch (e) { /* non-critical */ }
      }
      return result;
    };
  }

  // ── Nav menu ─────────────────────────────────────────────────────
  // Proxy clicks to the original header buttons so all existing wiring
  // (toggle behavior, overlay close coordination, focus handling) runs.
  const NAV_PROXY = {
    history: 'hist-btn',
    options: 'options-btn',
    theme: 'theme-btn',
    faq: 'faq-btn',
  };
  railNav?.addEventListener('click', e => {
    const item = e.target.closest?.('[data-action]');
    if (!item) return;
    const action = item.dataset.action;
    if (action === 'diag') return; // native <a> navigation
    e.preventDefault();
    const targetId = NAV_PROXY[action];
    if (!targetId) return;
    const target = document.getElementById(targetId);
    if (target) target.click();
  });

  // ── HUD: status cell toggle (debug affordance; safe no-op elsewhere) ──
  // Clicking the status cell is a design affordance for toggling mock state.
  // In the real app, status is driven by runner.js — leave this inert unless
  // no run is active, so curious users can't desync the runtime.
  hudStatusCell?.addEventListener('click', () => {
    // Intentionally no-op: status reflects runner state and must not be
    // forced from UI. Left in place to preserve cursor affordance.
  });

  // ── Init ─────────────────────────────────────────────────────────
  applyCollapsed();
  applyWidth();
  applySectionsState();
  renderRailRecent();

  // Expose the workflows renderer for controller.js to call after /workflows loads.
  global.renderRailWorkflows = renderRailWorkflows;
  global.renderRailRecent = renderRailRecent;

})(globalThis);
