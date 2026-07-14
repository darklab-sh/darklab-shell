// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Shared horizontal tab-strip overflow-edge controller.
//
// Mobile tab rows in the shell (Projects detail tabs, Atlas tabs, future
// surfaces) all use the same affordance: when the strip can scroll further
// in a direction, the wrap element shows a gradient mask on that edge.
// Before this helper existed, Projects owned its own
// `_syncProjectMobileTabEdges` + `_syncProjectMobileActiveTabScroll` pair
// hard-coded to `.project-mobile-tabs-wrap`, and copying that pattern for
// Atlas would have duplicated the scroll-into-view math and the
// `has-left-overflow` / `has-right-overflow` toggling.
//
// The contract:
//   - The strip is a horizontally scrolling element.
//   - The wrap is the strip's nearest ancestor matching `wrapSelector`
//     (default `.tab-strip-wrap`) and carries the overflow-edge classes.
//   - `syncTabStripEdges(strip, opts)` reads `scrollLeft` / `scrollWidth`
//     / `clientWidth` and toggles the two classes on the wrap.
//   - `syncActiveTabStripScroll(strip, opts)` centers the active tab
//     (selector defaults to `.is-active`) inside the strip on the next
//     frame, then syncs the edges. Pass `scrollOnlyIfNeeded` to leave
//     an already-visible active tab in place.
//   - `bindTabStripEdgeListener(strip, opts)` attaches a passive scroll
//     listener that re-syncs the edges and returns a teardown function.
//
// Callers pass their wrap selector explicitly so the helper does not have
// to know about feature-named classes; both Projects and Atlas wraps
// compose the shared `.tab-strip-wrap` primitive plus their feature-named
// class for layout overrides, so the default selector works for both.
const DarklabTabStripEdges = (function (global) {
  'use strict';

  const EDGE_THRESHOLD = 2;

  function syncTabStripEdges(strip, opts) {
    if (!strip || typeof strip.closest !== 'function') return;
    const options = opts || {};
    const wrapSelector = options.wrapSelector || '.tab-strip-wrap';
    const wrap = strip.closest(wrapSelector);
    if (!wrap) return;
    const maxScroll = Math.max(0, strip.scrollWidth - strip.clientWidth);
    const scrollLeft = Math.max(0, strip.scrollLeft || 0);
    wrap.classList.toggle('has-left-overflow', scrollLeft > EDGE_THRESHOLD);
    wrap.classList.toggle('has-right-overflow', scrollLeft < maxScroll - EDGE_THRESHOLD);
  }

  function syncActiveTabStripScroll(strip, opts) {
    if (!strip) return;
    const options = opts || {};
    const activeSelector = options.activeSelector || '.is-active';
    const active = strip.querySelector(activeSelector);
    if (!active) {
      syncTabStripEdges(strip, options);
      return;
    }
    window.setTimeout(() => {
      if (options.scrollOnlyIfNeeded) {
        const viewLeft = Math.max(0, strip.scrollLeft || 0);
        const viewRight = viewLeft + Math.max(0, strip.clientWidth || 0);
        const activeLeft = Math.max(0, active.offsetLeft || 0);
        const activeRight = activeLeft + Math.max(0, active.offsetWidth || 0);
        if (activeLeft >= viewLeft && activeRight <= viewRight) {
          syncTabStripEdges(strip, options);
          return;
        }
      }
      const offset = Math.max(0, (strip.clientWidth - active.offsetWidth) / 2);
      strip.scrollLeft = Math.max(0, active.offsetLeft - offset);
      syncTabStripEdges(strip, options);
    }, 0);
  }

  function bindTabStripEdgeListener(strip, opts) {
    if (!strip || typeof strip.addEventListener !== 'function') {
      return () => {};
    }
    if (strip.dataset && strip.dataset.tabStripEdgeBound === '1') {
      return () => {};
    }
    const handler = () => syncTabStripEdges(strip, opts);
    strip.addEventListener('scroll', handler, { passive: true });
    if (strip.dataset) strip.dataset.tabStripEdgeBound = '1';
    return () => {
      strip.removeEventListener('scroll', handler);
      if (strip.dataset) delete strip.dataset.tabStripEdgeBound;
    };
  }

  return Object.freeze({
    bindTabStripEdgeListener,
    syncActiveTabStripScroll,
    syncTabStripEdges,
  });
})(typeof window !== 'undefined' ? window : globalThis);

export const { bindTabStripEdgeListener, syncActiveTabStripScroll, syncTabStripEdges } = DarklabTabStripEdges;
export { DarklabTabStripEdges };
