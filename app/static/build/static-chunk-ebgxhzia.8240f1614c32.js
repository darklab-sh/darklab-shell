// app/static/js/ui/ui_tab_strip_edges.js
var DarklabTabStripEdges = (function(global) {
  "use strict";
  const EDGE_THRESHOLD = 2;
  function syncTabStripEdges2(strip, opts) {
    if (!strip || typeof strip.closest !== "function") return;
    const options = opts || {};
    const wrapSelector = options.wrapSelector || ".tab-strip-wrap";
    const wrap = strip.closest(wrapSelector);
    if (!wrap) return;
    const maxScroll = Math.max(0, strip.scrollWidth - strip.clientWidth);
    const scrollLeft = Math.max(0, strip.scrollLeft || 0);
    wrap.classList.toggle("has-left-overflow", scrollLeft > EDGE_THRESHOLD);
    wrap.classList.toggle("has-right-overflow", scrollLeft < maxScroll - EDGE_THRESHOLD);
  }
  function syncActiveTabStripScroll2(strip, opts) {
    if (!strip) return;
    const options = opts || {};
    const activeSelector = options.activeSelector || ".is-active";
    const active = strip.querySelector(activeSelector);
    if (!active) {
      syncTabStripEdges2(strip, options);
      return;
    }
    window.setTimeout(() => {
      if (options.scrollOnlyIfNeeded) {
        const viewLeft = Math.max(0, strip.scrollLeft || 0);
        const viewRight = viewLeft + Math.max(0, strip.clientWidth || 0);
        const activeLeft = Math.max(0, active.offsetLeft || 0);
        const activeRight = activeLeft + Math.max(0, active.offsetWidth || 0);
        if (activeLeft >= viewLeft && activeRight <= viewRight) {
          syncTabStripEdges2(strip, options);
          return;
        }
      }
      const offset = Math.max(0, (strip.clientWidth - active.offsetWidth) / 2);
      strip.scrollLeft = Math.max(0, active.offsetLeft - offset);
      syncTabStripEdges2(strip, options);
    }, 0);
  }
  function bindTabStripEdgeListener2(strip, opts) {
    if (!strip || typeof strip.addEventListener !== "function") {
      return () => {
      };
    }
    if (strip.dataset && strip.dataset.tabStripEdgeBound === "1") {
      return () => {
      };
    }
    const handler = () => syncTabStripEdges2(strip, opts);
    strip.addEventListener("scroll", handler, { passive: true });
    if (strip.dataset) strip.dataset.tabStripEdgeBound = "1";
    return () => {
      strip.removeEventListener("scroll", handler);
      if (strip.dataset) delete strip.dataset.tabStripEdgeBound;
    };
  }
  return Object.freeze({
    bindTabStripEdgeListener: bindTabStripEdgeListener2,
    syncActiveTabStripScroll: syncActiveTabStripScroll2,
    syncTabStripEdges: syncTabStripEdges2
  });
})(typeof window !== "undefined" ? window : globalThis);
var { bindTabStripEdgeListener, syncActiveTabStripScroll, syncTabStripEdges } = DarklabTabStripEdges;

export {
  bindTabStripEdgeListener,
  syncActiveTabStripScroll,
  syncTabStripEdges
};
