import {
  activateTab
} from "./static-chunk-n2vpqjbs.2f664fbfac6b.js";
import "./static-chunk-poi5czx6.3f5c94749765.js";
import "./static-chunk-lxs2zdd2.87dc9e4c1317.js";
import "./static-chunk-fik64llj.1291b1f4f79b.js";
import "./static-chunk-yu6ty7m2.96c3ee208a44.js";
import {
  getActiveTabId,
  getTabs,
  onUiEvent
} from "./static-chunk-sgyzdmxn.7d1842f12a94.js";
import "./static-chunk-tym5o2af.a748583ae389.js";
import "./static-chunk-i34eiczq.4bb950c346dc.js";

// app/static/js/features/mobile/mobile_running_indicator.js
var global = typeof window !== "undefined" ? window : globalThis;
var createMobileRunningIndicator = null;
function _mobileRunningGetTabs() {
  if (typeof getTabs !== "undefined" && typeof getTabs === "function") return getTabs();
  return null;
}
function _mobileRunningGetActiveTabId() {
  if (typeof getActiveTabId !== "undefined" && typeof getActiveTabId === "function") {
    return getActiveTabId();
  }
  return null;
}
function _mobileRunningActivateTab(tabId, options) {
  const activate = typeof activateTab === "function" ? activateTab : null;
  if (typeof activate === "function") activate(tabId, options);
}
function _mobileRunningOnUiEvent(name, handler) {
  const subscribe = typeof onUiEvent === "function" ? onUiEvent : null;
  if (typeof subscribe === "function") subscribe(name, handler);
}
if (typeof document !== "undefined") {
  createMobileRunningIndicator = function createMobileRunningIndicator2({
    tabsBarEl = null,
    terminalBarEl = null
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
        runningChipEl = document.createElement("button");
        runningChipEl.type = "button";
        runningChipEl.id = "mobile-running-chip";
        runningChipEl.className = "mobile-running-chip u-hidden";
        runningChipEl.setAttribute("aria-label", "Cycle to next running tab");
        runningChipEl.title = "Cycle to next running tab";
        const dot = document.createElement("span");
        dot.className = "mobile-running-dot";
        dot.setAttribute("aria-hidden", "true");
        dot.textContent = "●";
        runningChipCountEl = document.createElement("span");
        runningChipCountEl.className = "mobile-running-count";
        runningChipCountEl.textContent = "0";
        runningChipEl.append(dot, runningChipCountEl);
        runningChipEl.addEventListener("click", onRunningChipTap);
        terminalBarEl.appendChild(runningChipEl);
      }
      if (!edgeGlowLeftEl && document.body) {
        edgeGlowLeftEl = document.createElement("span");
        edgeGlowLeftEl.className = "tab-edge-glow tab-edge-glow-left";
        edgeGlowLeftEl.setAttribute("aria-hidden", "true");
        document.body.appendChild(edgeGlowLeftEl);
      }
      if (!edgeGlowRightEl && document.body) {
        edgeGlowRightEl = document.createElement("span");
        edgeGlowRightEl.className = "tab-edge-glow tab-edge-glow-right";
        edgeGlowRightEl.setAttribute("aria-hidden", "true");
        document.body.appendChild(edgeGlowRightEl);
      }
    }
    function runningNonActiveTabs() {
      if (!tabsBarEl) return [];
      const tabsList = _mobileRunningGetTabs();
      if (!Array.isArray(tabsList)) return [];
      const activeId = _mobileRunningGetActiveTabId();
      const byId = new Map(tabsList.map((t) => [t.id, t]));
      const orderedIds = Array.from(tabsBarEl.querySelectorAll(".tab")).map((n) => n.dataset.id);
      return orderedIds.map((id) => byId.get(id)).filter((t) => !!t && t.st === "running" && t.id !== activeId);
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
      _mobileRunningActivateTab(next.id, { focusComposer: false });
      scrollTabIntoView(next.id);
    }
    function hideEdgeGlows() {
      if (edgeGlowLeftEl) edgeGlowLeftEl.classList.remove("is-active");
      if (edgeGlowRightEl) edgeGlowRightEl.classList.remove("is-active");
    }
    function syncEdgeGlows(running) {
      if (!tabsBarEl || !edgeGlowLeftEl || !edgeGlowRightEl) return;
      if (!running || running.length === 0) {
        hideEdgeGlows();
        return;
      }
      const barRect = tabsBarEl.getBoundingClientRect();
      const top = Math.round(barRect.top) + "px";
      const height = Math.round(barRect.height) + "px";
      edgeGlowLeftEl.style.top = top;
      edgeGlowLeftEl.style.height = height;
      edgeGlowLeftEl.style.left = Math.round(barRect.left) + "px";
      edgeGlowRightEl.style.top = top;
      edgeGlowRightEl.style.height = height;
      edgeGlowRightEl.style.left = Math.round(barRect.right - 22) + "px";
      let leftActive = false;
      let rightActive = false;
      for (const t of running) {
        const node = tabsBarEl.querySelector(`.tab[data-id="${t.id}"]`);
        if (!node) continue;
        const r = node.getBoundingClientRect();
        if (r.left < barRect.left + 4) leftActive = true;
        if (r.right > barRect.right - 4) rightActive = true;
      }
      edgeGlowLeftEl.classList.toggle("is-active", leftActive);
      edgeGlowRightEl.classList.toggle("is-active", rightActive);
    }
    function applyRunningState() {
      if (!terminalBarEl || !tabsBarEl) return;
      const isMobile = !!(document.body && document.body.classList.contains("mobile-terminal-mode"));
      if (!isMobile) {
        if (runningChipEl) runningChipEl.classList.add("u-hidden");
        hideEdgeGlows();
        return;
      }
      ensureMounts();
      const running = runningNonActiveTabs();
      const count = running.length;
      if (count === 0) {
        runningChipEl.classList.add("u-hidden");
        hideEdgeGlows();
        runningCycleIdx = 0;
        return;
      }
      runningChipEl.classList.remove("u-hidden");
      runningChipCountEl.textContent = String(count);
      syncEdgeGlows(running);
    }
    function sync() {
      if (runningSyncRaf) return;
      runningSyncRaf = (typeof requestAnimationFrame === "function" ? requestAnimationFrame : (cb) => setTimeout(cb, 16))(() => {
        runningSyncRaf = 0;
        applyRunningState();
      });
    }
    if (terminalBarEl && tabsBarEl) {
      ensureMounts();
      global.addEventListener?.("resize", sync);
      tabsBarEl.addEventListener("scroll", () => {
        if (scrollSyncTimer) clearTimeout(scrollSyncTimer);
        scrollSyncTimer = setTimeout(sync, 120);
      }, { passive: true });
    }
    _mobileRunningOnUiEvent("app:tab-created", () => sync());
    _mobileRunningOnUiEvent("app:tab-closed", () => sync());
    _mobileRunningOnUiEvent("app:tab-status-changed", () => sync());
    _mobileRunningOnUiEvent("app:tab-activated", () => sync());
    _mobileRunningOnUiEvent("app:tab-order-changed", () => sync());
    sync();
    return { sync };
  };
}
export {
  createMobileRunningIndicator
};
