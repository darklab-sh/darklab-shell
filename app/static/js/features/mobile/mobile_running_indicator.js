// Mobile non-active running-tab indicator.
//
// The mobile status pill reflects the active tab only; this surface gives a
// system-level signal that work is happening on a backgrounded tab.
(function initMobileRunningIndicator(global) {
  if (typeof document === 'undefined') return;

  function createMobileRunningIndicator({
    tabsBarEl = null,
    terminalBarEl = null,
  } = {}) {
    let runningChipEl = null;
    let runningChipCountEl = null;
    let edgeGlowLeftEl = null;
    let edgeGlowRightEl = null;
    let runningCycleIdx = 0;
    let runningSyncRaf = 0;
    let scrollSyncTimer = 0;

    function ensureMounts() {
      if (!terminalBarEl) return;
      if (!runningChipEl) {
        runningChipEl = document.createElement('button');
        runningChipEl.type = 'button';
        runningChipEl.id = 'mobile-running-chip';
        runningChipEl.className = 'mobile-running-chip u-hidden';
        runningChipEl.setAttribute('aria-label', 'Cycle to next running tab');
        runningChipEl.title = 'Cycle to next running tab';
        const dot = document.createElement('span');
        dot.className = 'mobile-running-dot';
        dot.setAttribute('aria-hidden', 'true');
        dot.textContent = '●';
        runningChipCountEl = document.createElement('span');
        runningChipCountEl.className = 'mobile-running-count';
        runningChipCountEl.textContent = '0';
        runningChipEl.append(dot, runningChipCountEl);
        runningChipEl.addEventListener('click', onRunningChipTap);
        terminalBarEl.appendChild(runningChipEl);
      }
      // Edge glows are position:fixed overlays parented to body so they never
      // live inside the tabs-bar flex/scroll chain, which destabilizes iOS
      // Safari momentum scroll.
      if (!edgeGlowLeftEl && document.body) {
        edgeGlowLeftEl = document.createElement('span');
        edgeGlowLeftEl.className = 'tab-edge-glow tab-edge-glow-left';
        edgeGlowLeftEl.setAttribute('aria-hidden', 'true');
        document.body.appendChild(edgeGlowLeftEl);
      }
      if (!edgeGlowRightEl && document.body) {
        edgeGlowRightEl = document.createElement('span');
        edgeGlowRightEl.className = 'tab-edge-glow tab-edge-glow-right';
        edgeGlowRightEl.setAttribute('aria-hidden', 'true');
        document.body.appendChild(edgeGlowRightEl);
      }
    }

    function runningNonActiveTabs() {
      if (!tabsBarEl) return [];
      const tabsList = (typeof global.getTabs === 'function') ? global.getTabs() : null;
      if (!Array.isArray(tabsList)) return [];
      const activeId = (typeof global.getActiveTabId === 'function') ? global.getActiveTabId() : null;
      const byId = new Map(tabsList.map(t => [t.id, t]));
      // Tab-row order is the visual order, not the array order. Drag-reorder
      // mutates the DOM but not the underlying tabs array.
      const orderedIds = Array.from(tabsBarEl.querySelectorAll('.tab')).map(n => n.dataset.id);
      return orderedIds
        .map(id => byId.get(id))
        .filter(t => !!t && t.st === 'running' && t.id !== activeId);
    }

    function scrollTabIntoView(id) {
      if (!tabsBarEl || !id) return;
      const node = tabsBarEl.querySelector(`.tab[data-id="${id}"]`);
      if (!node) return;
      const tabRect = node.getBoundingClientRect();
      const barRect = tabsBarEl.getBoundingClientRect();
      const visibleLeft = tabRect.left >= barRect.left;
      const visibleRight = tabRect.right <= barRect.right;
      if (visibleLeft && visibleRight) return;
      const tabLeftInContent = tabRect.left - barRect.left + tabsBarEl.scrollLeft;
      const centered = tabLeftInContent - (barRect.width - tabRect.width) / 2;
      const maxScroll = Math.max(0, tabsBarEl.scrollWidth - tabsBarEl.clientWidth);
      tabsBarEl.scrollLeft = Math.max(0, Math.min(maxScroll, centered));
    }

    function onRunningChipTap() {
      const running = runningNonActiveTabs();
      if (running.length === 0) return;
      const next = running[runningCycleIdx % running.length];
      runningCycleIdx += 1;
      const activate = (typeof global.activateTab === 'function') ? global.activateTab : null;
      if (activate) activate(next.id, { focusComposer: false });
      // activateTab uses smooth scroll, but iOS Safari can drop the first call
      // on a cold horizontal scroll container. Direct scrollLeft always lands.
      scrollTabIntoView(next.id);
    }

    function hideEdgeGlows() {
      if (edgeGlowLeftEl) edgeGlowLeftEl.classList.remove('is-active');
      if (edgeGlowRightEl) edgeGlowRightEl.classList.remove('is-active');
    }

    function syncEdgeGlows(running) {
      if (!tabsBarEl || !edgeGlowLeftEl || !edgeGlowRightEl) return;
      if (!running || running.length === 0) { hideEdgeGlows(); return; }
      const barRect = tabsBarEl.getBoundingClientRect();
      const top = Math.round(barRect.top) + 'px';
      const height = Math.round(barRect.height) + 'px';
      edgeGlowLeftEl.style.top = top;
      edgeGlowLeftEl.style.height = height;
      edgeGlowLeftEl.style.left = Math.round(barRect.left) + 'px';
      edgeGlowRightEl.style.top = top;
      edgeGlowRightEl.style.height = height;
      edgeGlowRightEl.style.left = Math.round(barRect.right - 22) + 'px';
      let leftActive = false;
      let rightActive = false;
      for (const t of running) {
        const node = tabsBarEl.querySelector(`.tab[data-id="${t.id}"]`);
        if (!node) continue;
        const r = node.getBoundingClientRect();
        if (r.left < barRect.left + 4) leftActive = true;
        if (r.right > barRect.right - 4) rightActive = true;
      }
      edgeGlowLeftEl.classList.toggle('is-active', leftActive);
      edgeGlowRightEl.classList.toggle('is-active', rightActive);
    }

    function applyRunningState() {
      if (!terminalBarEl || !tabsBarEl) return;
      const isMobile = !!(document.body && document.body.classList.contains('mobile-terminal-mode'));
      if (!isMobile) {
        if (runningChipEl) runningChipEl.classList.add('u-hidden');
        hideEdgeGlows();
        return;
      }
      ensureMounts();
      const running = runningNonActiveTabs();
      const count = running.length;
      if (count === 0) {
        runningChipEl.classList.add('u-hidden');
        hideEdgeGlows();
        runningCycleIdx = 0;
        return;
      }
      runningChipEl.classList.remove('u-hidden');
      runningChipCountEl.textContent = String(count);
      syncEdgeGlows(running);
    }

    function sync() {
      if (runningSyncRaf) return;
      runningSyncRaf = (typeof requestAnimationFrame === 'function'
        ? requestAnimationFrame
        : (cb) => setTimeout(cb, 16))(() => {
        runningSyncRaf = 0;
        applyRunningState();
      });
    }

    if (terminalBarEl && tabsBarEl) {
      ensureMounts();
      global.addEventListener?.('resize', sync);
      tabsBarEl.addEventListener('scroll', () => {
        if (scrollSyncTimer) clearTimeout(scrollSyncTimer);
        scrollSyncTimer = setTimeout(sync, 120);
      }, { passive: true });
    }
    if (typeof global.onUiEvent === 'function') {
      global.onUiEvent('app:tab-created', () => sync());
      global.onUiEvent('app:tab-closed', () => sync());
      global.onUiEvent('app:tab-status-changed', () => sync());
      global.onUiEvent('app:tab-activated', () => sync());
      global.onUiEvent('app:tab-order-changed', () => sync());
    }
    sync();

    return { sync };
  }

  global.DarklabMobileRunningIndicator = {
    create: createMobileRunningIndicator,
  };
})(typeof window !== 'undefined' ? window : this);
