import {
  bindPressable
} from "./static-chunk-fik64llj.1291b1f4f79b.js";

// app/static/js/ui/ui_disclosure.js
var bindDisclosure = (function(global) {
  "use strict";
  function _applyPanelState(panel, open, openClass, hiddenClass) {
    if (!panel || !panel.classList) return;
    if (openClass) panel.classList.toggle(openClass, open);
    if (hiddenClass) panel.classList.toggle(hiddenClass, !open);
  }
  function bindDisclosure2(trigger, opts) {
    if (!trigger || !opts) return null;
    if (trigger.dataset && trigger.dataset.disclosureBound === "1") return null;
    const pressable = typeof bindPressable === "function" ? bindPressable : null;
    if (!pressable) return null;
    const panel = opts.panel || null;
    const openClass = Object.prototype.hasOwnProperty.call(opts, "openClass") ? opts.openClass : "open";
    const hiddenClass = opts.hiddenClass || null;
    const onToggle = typeof opts.onToggle === "function" ? opts.onToggle : null;
    let isOpen = !!opts.initialOpen;
    function sync(emit) {
      if (typeof trigger.setAttribute === "function") {
        trigger.setAttribute("aria-expanded", isOpen ? "true" : "false");
      }
      _applyPanelState(panel, isOpen, openClass, hiddenClass);
      if (emit && onToggle) onToggle(isOpen, { trigger, panel });
    }
    sync(false);
    pressable(trigger, {
      refocusComposer: opts.refocusComposer === true,
      clearPressStyle: !!opts.clearPressStyle,
      preventFocusTheft: !!opts.preventFocusTheft,
      preventScroll: opts.preventScroll,
      defer: opts.defer,
      onActivate: (e) => {
        if (opts.stopPropagation && e && typeof e.stopPropagation === "function") {
          e.stopPropagation();
        }
        isOpen = !isOpen;
        sync(true);
      }
    });
    if (trigger.dataset) trigger.dataset.disclosureBound = "1";
    return {
      isOpen: () => isOpen,
      open: () => {
        if (!isOpen) {
          isOpen = true;
          sync(true);
        }
      },
      close: () => {
        if (isOpen) {
          isOpen = false;
          sync(true);
        }
      },
      toggle: () => {
        isOpen = !isOpen;
        sync(true);
      }
    };
  }
  return bindDisclosure2;
})(typeof window !== "undefined" ? window : globalThis);

export {
  bindDisclosure
};
