import {
  useMobileTerminalViewportMode
} from "./static-chunk-2bgb52uq.a327269283bb.js";
import {
  enhanceAppSelects,
  hideModalOverlay,
  refocusComposerAfterAction,
  showModalOverlay
} from "./static-chunk-yo5cjr7d.b86e0c93eff0.js";

// app/static/js/ui/mobile_sheet.js
var bindMobileSheet = (function(global) {
  "use strict";
  function _isMobileMode() {
    const readMobileMode = typeof useMobileTerminalViewportMode !== "undefined" && useMobileTerminalViewportMode || null;
    if (typeof readMobileMode === "function" && readMobileMode()) return true;
    return !!(typeof document !== "undefined" && document.body && document.body.classList && document.body.classList.contains("mobile-terminal-mode"));
  }
  function _ensureGrab(sheet) {
    if (!sheet) return null;
    let grab = sheet.querySelector(":scope > .sheet-grab");
    if (grab) return grab;
    grab = document.createElement("div");
    grab.className = "sheet-grab gesture-handle";
    grab.setAttribute("aria-hidden", "true");
    sheet.insertBefore(grab, sheet.firstChild || null);
    return grab;
  }
  function bindMobileSheet2(sheet, opts) {
    if (!sheet || !opts || typeof opts.onClose !== "function") return;
    if (sheet.dataset.mobileSheetBound === "1") return;
    sheet.dataset.mobileSheetBound = "1";
    const onClose = opts.onClose;
    const threshold = typeof opts.threshold === "number" ? opts.threshold : 60;
    const tapMaxMovement = typeof opts.tapMaxMovement === "number" ? opts.tapMaxMovement : 10;
    const grab = _ensureGrab(sheet);
    if (!grab) return;
    let drag = null;
    function clearStyles() {
      sheet.style.removeProperty("transform");
      sheet.style.removeProperty("transition");
      sheet.style.removeProperty("will-change");
      sheet.style.removeProperty("opacity");
    }
    function fallbackCloseOpenOverlay() {
      const overlay = sheet.closest?.(".mobile-sheet-overlay.open");
      if (!overlay) return;
      overlay.classList.remove("open");
      overlay.classList.add("u-hidden");
      overlay.setAttribute("aria-hidden", "true");
    }
    function settle(close) {
      if (close) {
        sheet.style.transition = "transform 180ms ease, opacity 180ms ease";
        sheet.style.transform = `translateY(${sheet.getBoundingClientRect().height}px)`;
        sheet.style.opacity = "0.98";
        setTimeout(() => {
          clearStyles();
          try {
            onClose();
          } finally {
            fallbackCloseOpenOverlay();
          }
        }, 180);
      } else {
        sheet.style.transition = "transform 160ms ease";
        sheet.style.transform = "translateY(0)";
        setTimeout(clearStyles, 180);
      }
    }
    function _removeWindowFallbacks() {
      window.removeEventListener("pointerup", _windowEnd, true);
      window.removeEventListener("pointercancel", _windowCancel, true);
    }
    function endDrag(pointerId, cancelled) {
      if (!drag || drag.pointerId !== pointerId) return;
      const dy = drag.dy;
      const moved = drag.maxDy;
      drag = null;
      _removeWindowFallbacks();
      try {
        sheet.releasePointerCapture(pointerId);
      } catch (_) {
      }
      try {
        grab.releasePointerCapture(pointerId);
      } catch (_) {
      }
      if (cancelled) {
        settle(false);
        return;
      }
      if (moved < tapMaxMovement) {
        clearStyles();
        onClose();
        return;
      }
      settle(dy >= threshold);
    }
    function applyPointerPosition(e) {
      if (!drag || drag.pointerId !== e.pointerId) return;
      const dy = Math.max(0, e.clientY - drag.startY);
      drag.dy = dy;
      if (dy > drag.maxDy) drag.maxDy = dy;
      if (dy > 0) sheet.style.transform = `translateY(${dy}px)`;
    }
    function _windowEnd(e) {
      applyPointerPosition(e);
      endDrag(e.pointerId, false);
    }
    function _windowCancel(e) {
      endDrag(e.pointerId, true);
    }
    function _isGrabEvent(e) {
      return e && (e.target === grab || typeof e.composedPath === "function" && e.composedPath().includes(grab));
    }
    grab.addEventListener("pointerdown", (e) => {
      if (!_isMobileMode()) return;
      if (typeof e.button === "number" && e.button !== 0) return;
      clearStyles();
      drag = { pointerId: e.pointerId, startY: e.clientY, dy: 0, maxDy: 0 };
      sheet.style.willChange = "transform";
      sheet.style.transition = "none";
      try {
        grab.setPointerCapture(e.pointerId);
      } catch (_) {
      }
      window.addEventListener("pointerup", _windowEnd, true);
      window.addEventListener("pointercancel", _windowCancel, true);
    });
    const onPointerMove = (e) => {
      if (!drag || drag.pointerId !== e.pointerId) return;
      applyPointerPosition(e);
      if (drag.dy <= 0) return;
      e.preventDefault();
    };
    grab.addEventListener("pointermove", onPointerMove);
    grab.addEventListener("pointerup", (e) => {
      applyPointerPosition(e);
      endDrag(e.pointerId, false);
    });
    grab.addEventListener("pointercancel", (e) => endDrag(e.pointerId, true));
    sheet.addEventListener("pointermove", (e) => {
      if (_isGrabEvent(e)) onPointerMove(e);
    }, true);
    sheet.addEventListener("pointerup", (e) => {
      if (_isGrabEvent(e)) {
        applyPointerPosition(e);
        endDrag(e.pointerId, false);
      }
    }, true);
    sheet.addEventListener("pointercancel", (e) => {
      if (_isGrabEvent(e)) endDrag(e.pointerId, true);
    }, true);
    grab.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onClose();
      }
    });
    let _lastHidden = !_isVisible(sheet);
    const visibilityObserver = new MutationObserver(() => {
      const hidden = !_isVisible(sheet);
      if (hidden && !_lastHidden) {
        drag = null;
        _removeWindowFallbacks();
        clearStyles();
      }
      _lastHidden = hidden;
    });
    visibilityObserver.observe(sheet, { attributes: true, attributeFilter: ["class", "style"] });
    if (sheet.parentElement) {
      visibilityObserver.observe(sheet.parentElement, { attributes: true, attributeFilter: ["class", "style"] });
    }
  }
  function _isVisible(el) {
    if (!el || typeof el.getClientRects !== "function") return false;
    if (el.offsetParent === null && getComputedStyle(el).position !== "fixed") {
      const rects = el.getClientRects();
      if (!rects.length) return false;
    }
    return getComputedStyle(el).display !== "none" && getComputedStyle(el).visibility !== "hidden";
  }
  return bindMobileSheet2;
})(typeof window !== "undefined" ? window : globalThis);

// app/static/js/ui/ui_action_sheet.js
var {
  closeActionSheet,
  openActionSheet
} = /* @__PURE__ */ (function initActionSheet() {
  let overlay = null;
  let sheet = null;
  let titleEl = null;
  let itemsEl = null;
  let returnFocusEl = null;
  let onCloseFn = null;
  function _ensure() {
    if (overlay && sheet && titleEl && itemsEl) return overlay;
    overlay = document.createElement("div");
    overlay.id = "action-sheet-overlay";
    overlay.className = "modal-overlay mobile-sheet-overlay action-sheet-overlay u-hidden";
    overlay.setAttribute("aria-hidden", "true");
    sheet = document.createElement("section");
    sheet.id = "action-sheet";
    sheet.className = "modal-card mobile-sheet-surface bottom-sheet action-sheet";
    sheet.setAttribute("role", "dialog");
    sheet.setAttribute("aria-modal", "true");
    sheet.setAttribute("aria-labelledby", "action-sheet-title");
    const grab = document.createElement("div");
    grab.className = "sheet-grab gesture-handle";
    grab.setAttribute("role", "button");
    grab.tabIndex = 0;
    grab.setAttribute("aria-label", "Close action sheet");
    const header = document.createElement("div");
    header.className = "bottom-sheet-header action-sheet-header";
    titleEl = document.createElement("h2");
    titleEl.id = "action-sheet-title";
    titleEl.className = "action-sheet-title";
    titleEl.textContent = "Actions";
    header.appendChild(titleEl);
    itemsEl = document.createElement("div");
    itemsEl.className = "bottom-sheet-body nice-scroll action-sheet-items";
    sheet.append(grab, header, itemsEl);
    overlay.appendChild(sheet);
    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) closeActionSheet2();
    });
    const dismissible = typeof bindDismissible === "function" ? bindDismissible : null;
    if (dismissible) {
      dismissible(overlay, {
        level: "sheet",
        isOpen: () => !!(overlay && overlay.classList.contains("open")),
        onClose: () => closeActionSheet2(),
        backdropEl: overlay
      });
    }
    const mobileSheet = typeof bindMobileSheet === "function" ? bindMobileSheet : null;
    if (mobileSheet) {
      mobileSheet(sheet, { onClose: () => closeActionSheet2() });
    }
    return overlay;
  }
  function _mount(container) {
    const host = container && typeof container.appendChild === "function" ? container : document.body;
    if (overlay && overlay.parentElement !== host) host.appendChild(overlay);
  }
  function _actionButton(item) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-ghost action-sheet-item";
    if (item.tone === "danger") btn.classList.add("is-danger", "btn-danger");
    if (item.disabled) btn.disabled = true;
    if (item.action) btn.dataset.actionSheetAction = String(item.action);
    if (item.title || item.hint) btn.title = item.title || item.hint;
    if (item.icon) {
      const icon = document.createElement("span");
      icon.className = "action-sheet-item-icon";
      icon.setAttribute("aria-hidden", "true");
      icon.textContent = String(item.icon);
      btn.appendChild(icon);
    }
    const label = document.createElement("span");
    label.textContent = String(item.label || "");
    btn.appendChild(label);
    btn.addEventListener("click", async () => {
      if (btn.disabled) return;
      btn.disabled = true;
      closeActionSheet2({ restoreFocus: false });
      if (typeof item.action === "function") {
        await item.action(item);
      }
    });
    const pressable = typeof bindPressable === "function" ? bindPressable : null;
    if (pressable) {
      pressable(btn, { refocusComposer: false });
    }
    return btn;
  }
  function _renderItem(item) {
    if (!item) return null;
    if (item.divider) {
      const divider = document.createElement("div");
      divider.className = "action-sheet-divider";
      divider.setAttribute("role", "separator");
      return divider;
    }
    if (item.node) {
      const wrap = document.createElement("div");
      wrap.className = "action-sheet-field";
      wrap.appendChild(item.node);
      return wrap;
    }
    return _actionButton(item);
  }
  function openActionSheet2({
    title = "Actions",
    items = [],
    container = document.body,
    onClose = null,
    returnFocus = null
  } = {}) {
    const filteredItems = Array.isArray(items) ? items.filter(Boolean) : [];
    if (!filteredItems.length) return null;
    closeActionSheet2({ restoreFocus: false });
    _ensure();
    _mount(container);
    onCloseFn = typeof onClose === "function" ? onClose : null;
    returnFocusEl = returnFocus || document.activeElement || null;
    titleEl.textContent = String(title || "Actions");
    itemsEl.replaceChildren();
    filteredItems.forEach((item) => {
      const node = _renderItem(item);
      if (node) itemsEl.appendChild(node);
    });
    const enhanceAppSelects2 = typeof enhanceAppSelects === "function" ? enhanceAppSelects : null;
    if (typeof enhanceAppSelects2 === "function") {
      itemsEl.querySelectorAll("select.form-select").forEach((select) => {
        select.dataset.portalMenu = "true";
      });
      enhanceAppSelects2(itemsEl);
    }
    overlay.classList.remove("u-hidden");
    overlay.classList.add("open");
    overlay.setAttribute("aria-hidden", "false");
    itemsEl.scrollTop = 0;
    window.setTimeout(() => {
      itemsEl.querySelector("button:not(:disabled), select:not(:disabled), input:not(:disabled), textarea:not(:disabled)")?.focus();
    }, 0);
    return overlay;
  }
  function closeActionSheet2({ restoreFocus = true } = {}) {
    if (!overlay) return;
    overlay.classList.add("u-hidden");
    overlay.classList.remove("open");
    overlay.setAttribute("aria-hidden", "true");
    if (itemsEl) itemsEl.replaceChildren();
    const focusTarget = returnFocusEl;
    const onClose = onCloseFn;
    returnFocusEl = null;
    onCloseFn = null;
    if (typeof onClose === "function") onClose();
    if (restoreFocus && focusTarget && focusTarget.isConnected && typeof focusTarget.focus === "function") {
      window.setTimeout(() => focusTarget.focus(), 0);
    }
  }
  return {
    closeActionSheet: closeActionSheet2,
    openActionSheet: openActionSheet2
  };
})();

// app/static/js/ui/ui_focus_trap.js
var bindFocusTrap = (function() {
  "use strict";
  const FOCUSABLE_SELECTOR = [
    "button:not([disabled])",
    "a[href]",
    "input:not([disabled])",
    "select:not([disabled])",
    "textarea:not([disabled])",
    '[tabindex]:not([tabindex="-1"])'
  ].join(", ");
  function _isVisible(el) {
    if (!el) return false;
    if (el.hidden) return false;
    if (typeof el.closest === "function" && el.closest("[hidden]")) return false;
    if (typeof window !== "undefined" && typeof window.getComputedStyle === "function") {
      let node = el;
      while (node && node.nodeType === 1) {
        const style = window.getComputedStyle(node);
        if (style && (style.display === "none" || style.visibility === "hidden" || style.visibility === "collapse")) {
          return false;
        }
        node = node.parentElement;
      }
    }
    return true;
  }
  function _focusables(container) {
    if (!container || typeof container.querySelectorAll !== "function") return [];
    const nodes = Array.from(container.querySelectorAll(FOCUSABLE_SELECTOR));
    return nodes.filter(_isVisible);
  }
  function bindFocusTrap2(container, opts) {
    if (!container) return null;
    if (container.dataset && container.dataset.focusTrapBound === "1") return null;
    if (container.dataset) container.dataset.focusTrapBound = "1";
    const arrowKeysEnabled = !!(opts && opts.arrowKeys);
    const keydownHandler = (e) => {
      const list = _focusables(container);
      if (list.length === 0) return;
      const active = document.activeElement;
      const first = list[0];
      const last = list[list.length - 1];
      if (e.key === "Tab") {
        if (e.altKey || e.ctrlKey || e.metaKey) return;
        if (e.shiftKey) {
          if (active === first || !container.contains(active)) {
            e.preventDefault();
            if (typeof last.focus === "function") last.focus();
          }
        } else {
          if (active === last || !container.contains(active)) {
            e.preventDefault();
            if (typeof first.focus === "function") first.focus();
          }
        }
        return;
      }
      if (!arrowKeysEnabled) return;
      if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
      if (e.key !== "ArrowRight" && e.key !== "ArrowDown" && e.key !== "ArrowLeft" && e.key !== "ArrowUp") return;
      const currentIndex = list.indexOf(active);
      const movingForward = e.key === "ArrowRight" || e.key === "ArrowDown";
      let nextIndex = 0;
      if (currentIndex !== -1) {
        nextIndex = movingForward ? (currentIndex + 1) % list.length : (currentIndex - 1 + list.length) % list.length;
      } else {
        nextIndex = movingForward ? 0 : list.length - 1;
      }
      const next = list[nextIndex];
      if (next && typeof next.focus === "function") {
        e.preventDefault();
        next.focus();
      }
    };
    container.addEventListener("keydown", keydownHandler);
    return {
      dispose: () => {
        container.removeEventListener("keydown", keydownHandler);
        if (container.dataset) delete container.dataset.focusTrapBound;
      }
    };
  }
  return bindFocusTrap2;
})();

// app/static/js/ui/ui_confirm.js
(function(global) {
  "use strict";
  const STACKED_BREAKPOINT = 480;
  let _activeState = null;
  let _host = null;
  let _card = null;
  let _bodyEl = null;
  let _contentEl = null;
  let _actionsEl = null;
  function _getHost() {
    if (_host) return _host;
    _host = document.getElementById("confirm-host");
    if (!_host) return null;
    _card = _host.querySelector("[data-confirm-card]");
    _bodyEl = _host.querySelector("[data-confirm-body]");
    _contentEl = _host.querySelector("[data-confirm-content]");
    _actionsEl = _host.querySelector("[data-confirm-actions]");
    return _host;
  }
  function _isOpen() {
    return !!_activeState;
  }
  function _classForAction(action) {
    const role = action.role || "secondary";
    const tone = action.tone || null;
    let cls = "btn";
    if (role === "primary") cls += " btn-primary";
    else if (role === "ghost") cls += " btn-ghost";
    else if (role === "destructive") cls += " btn-destructive";
    else cls += " btn-secondary";
    if (role !== "destructive" && tone === "danger") cls += " btn-danger";
    else if (tone === "warning") cls += " btn-warning";
    return cls;
  }
  function _renderBody(target, body) {
    target.innerHTML = "";
    if (body === void 0 || body === null || body === "") return;
    if (typeof body === "string") {
      target.textContent = body;
      return;
    }
    if (body instanceof Node) {
      target.appendChild(body);
      return;
    }
    if (typeof body === "object" && (typeof body.text === "string" || typeof body.note === "string")) {
      if (typeof body.text === "string" && body.text !== "") {
        target.appendChild(document.createTextNode(body.text));
      }
      if (typeof body.note === "string" && body.note !== "") {
        if (target.childNodes.length > 0) target.appendChild(document.createElement("br"));
        const note = document.createElement("span");
        note.className = "modal-copy-note";
        note.textContent = body.note;
        target.appendChild(note);
      }
      return;
    }
    target.textContent = String(body);
  }
  function _renderContent(target, content) {
    target.innerHTML = "";
    if (content === void 0 || content === null) return;
    const nodes = Array.isArray(content) ? content : [content];
    nodes.forEach((node) => {
      if (node instanceof Node) target.appendChild(node);
    });
  }
  function _shouldStack(actionCount) {
    if (actionCount >= 3) return true;
    if (typeof window === "undefined" || !window.matchMedia) return false;
    return window.matchMedia(`(max-width: ${STACKED_BREAKPOINT}px)`).matches;
  }
  function _applyStacking(actionCount) {
    if (!_actionsEl) return;
    _actionsEl.classList.toggle("modal-actions-stacked", _shouldStack(actionCount));
  }
  function _resolveDefaultFocusTarget(target) {
    if (!target || !target.classList || !target.classList.contains("app-select-native")) return target;
    const wrap = target.nextElementSibling;
    if (!wrap || !wrap.classList || !wrap.classList.contains("app-select")) return target;
    return wrap.querySelector(".app-select-trigger") || target;
  }
  function _cleanup(state) {
    if (!_host) return;
    if (state && state.mqList && typeof state.mqList.remove === "function") state.mqList.remove();
    if (state && state.keydownHandle && typeof state.keydownHandle.remove === "function") {
      state.keydownHandle.remove();
    }
    if (state && state.focusTrapHandle && typeof state.focusTrapHandle.dispose === "function") {
      state.focusTrapHandle.dispose();
    }
    if (state && state.dismissibleHandle && typeof state.dismissibleHandle.dispose === "function") {
      state.dismissibleHandle.dispose();
    }
    if (typeof hideModalOverlay === "function") {
      hideModalOverlay(_host);
    } else if (_host.style) {
      _host.style.display = "none";
    }
    _host.classList.add("u-hidden");
    if (_card) _card.classList.remove("modal-card-danger", "modal-card-warning");
    if (_actionsEl) {
      _actionsEl.innerHTML = "";
      _actionsEl.classList.remove("modal-actions-stacked");
    }
    if (_bodyEl) _bodyEl.innerHTML = "";
    if (_contentEl) _contentEl.innerHTML = "";
  }
  function _resolveWith(value) {
    if (!_activeState) return;
    const state = _activeState;
    _activeState = null;
    try {
      _cleanup(state);
    } finally {
      if (state.refocusOnResolve !== false && typeof refocusComposerAfterAction === "function") {
        refocusComposerAfterAction({ defer: true });
      }
      state.resolve(value);
    }
  }
  function showConfirm2(opts) {
    const host = _getHost();
    if (!host) return Promise.reject(new Error("showConfirm: #confirm-host not present"));
    if (_isOpen()) return Promise.reject(new Error("showConfirm: another confirm is already open"));
    if (typeof closeActionSheet === "function") {
      closeActionSheet({ restoreFocus: false });
    }
    const body = opts && opts.body !== void 0 ? opts.body : "";
    const content = opts && opts.content !== void 0 ? opts.content : null;
    const tone = opts && opts.tone ? opts.tone : null;
    const actions = opts && Array.isArray(opts.actions) ? opts.actions.filter((a) => a && a.id) : [];
    if (actions.length === 0) return Promise.reject(new Error("showConfirm: actions required"));
    _renderBody(_bodyEl, body);
    if (_contentEl) _renderContent(_contentEl, content);
    if (_contentEl && typeof enhanceAppSelects === "function") {
      _contentEl.querySelectorAll("select.form-select").forEach((select) => {
        select.dataset.portalMenu = "true";
      });
      enhanceAppSelects(_contentEl);
    }
    _card.classList.remove("modal-card-danger", "modal-card-warning");
    if (tone === "danger") _card.classList.add("modal-card-danger");
    else if (tone === "warning") _card.classList.add("modal-card-warning");
    _actionsEl.innerHTML = "";
    const buttons = [];
    actions.forEach((action) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = _classForAction(action);
      btn.textContent = action.label || "";
      btn.dataset.confirmActionId = action.id;
      if (action.role === "cancel") btn.dataset.confirmRole = "cancel";
      btn.addEventListener("click", async (event) => {
        event.preventDefault();
        event.stopPropagation();
        if (typeof action.onActivate === "function") {
          let result;
          try {
            result = action.onActivate();
          } catch (_) {
            return;
          }
          if (result && typeof result.then === "function") {
            try {
              result = await result;
            } catch (_) {
              return;
            }
          }
          if (!result) return;
        }
        _resolveWith(action.id);
      });
      _actionsEl.appendChild(btn);
      buttons.push({ btn, action });
    });
    _applyStacking(actions.length);
    const activateDefaultAction = (event) => {
      if (!event || event.key !== "Enter") return;
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      const active = document.activeElement;
      const activeInsideHost = active && host.contains(active);
      const editableInsideHost = activeInsideHost && active.matches?.('input, textarea, select, [contenteditable="true"]');
      if (editableInsideHost) return;
      const activeButton = activeInsideHost && active?.matches?.("[data-confirm-action-id]") ? active : null;
      const cancel = buttons.find(({ action }) => action.role === "cancel");
      const target = activeButton || cancel && cancel.btn || buttons[0] && buttons[0].btn;
      if (!target || typeof target.click !== "function") return;
      event.preventDefault();
      event.stopPropagation();
      target.click();
    };
    document.addEventListener("keydown", activateDefaultAction, true);
    host.classList.remove("u-hidden");
    if (typeof showModalOverlay === "function") {
      showModalOverlay(host, "flex");
    } else if (host.style) {
      host.style.display = "flex";
    }
    let resolveFn;
    const promise = new Promise((resolve) => {
      resolveFn = resolve;
    });
    const state = {
      resolve: resolveFn,
      dismissibleHandle: null,
      focusTrapHandle: null,
      mqList: null,
      keydownHandle: { remove: () => document.removeEventListener("keydown", activateDefaultAction, true) },
      refocusOnResolve: opts.refocusOnResolve !== false
    };
    _activeState = state;
    if (typeof bindFocusTrap === "function" && _card) {
      state.focusTrapHandle = bindFocusTrap(_card, { arrowKeys: true });
    }
    if (typeof bindDismissible === "function") {
      state.dismissibleHandle = bindDismissible(host, {
        level: "modal",
        isOpen: _isOpen,
        onClose: () => _resolveWith(null),
        closeOnBackdrop: true
      });
    }
    if (typeof bindMobileSheet === "function" && _card) {
      bindMobileSheet(_card, { onClose: () => _resolveWith(null) });
    }
    if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
      const mq = window.matchMedia(`(max-width: ${STACKED_BREAKPOINT}px)`);
      const handler = () => _applyStacking(actions.length);
      if (typeof mq.addEventListener === "function") {
        mq.addEventListener("change", handler);
        state.mqList = { remove: () => mq.removeEventListener("change", handler) };
      } else if (typeof mq.addListener === "function") {
        mq.addListener(handler);
        state.mqList = { remove: () => mq.removeListener(handler) };
      }
    }
    let focusTarget = null;
    if (opts.defaultFocus instanceof Node) {
      focusTarget = _resolveDefaultFocusTarget(opts.defaultFocus);
    } else if (typeof opts.defaultFocus === "string" && opts.defaultFocus) {
      const explicit = buttons.find(({ action }) => action.id === opts.defaultFocus);
      if (explicit) focusTarget = explicit.btn;
    }
    if (!focusTarget) {
      const cancel = buttons.find(({ action }) => action.role === "cancel");
      if (cancel) focusTarget = cancel.btn;
    }
    if (!focusTarget && buttons.length) focusTarget = buttons[0].btn;
    if (focusTarget && typeof focusTarget.focus === "function") {
      const applyFocus = () => {
        const active = document.activeElement;
        if (active && active !== focusTarget && typeof active.blur === "function") {
          try {
            active.blur();
          } catch (_) {
          }
        }
        try {
          focusTarget.focus();
        } catch (_) {
        }
      };
      applyFocus();
      setTimeout(applyFocus, 0);
    }
    return promise;
  }
  function cancelConfirm2() {
    _resolveWith(null);
  }
  function isConfirmOpen2() {
    return _isOpen();
  }
  Object.assign(global, {
    cancelConfirm: cancelConfirm2,
    isConfirmOpen: isConfirmOpen2,
    showConfirm: showConfirm2
  });
})(typeof window !== "undefined" ? window : globalThis);
var confirmGlobal = typeof window !== "undefined" ? window : globalThis;
var showConfirm = confirmGlobal.showConfirm;
var cancelConfirm = confirmGlobal.cancelConfirm;
var isConfirmOpen = confirmGlobal.isConfirmOpen;

// app/static/js/ui/ui_pressable.js
var bindPressable = (function(global) {
  "use strict";
  function _isNativeButton(el) {
    return el && typeof el.tagName === "string" && el.tagName.toUpperCase() === "BUTTON";
  }
  function _clearPress(el) {
    if (!el || !el.dataset) return;
    el.dataset.pressableClearing = "1";
    const clear = () => {
      if (el.dataset) delete el.dataset.pressableClearing;
    };
    if (typeof requestAnimationFrame === "function") {
      requestAnimationFrame(() => requestAnimationFrame(clear));
    } else {
      setTimeout(clear, 16);
    }
  }
  function _afterActivate(el, options) {
    if (document.activeElement === el && typeof el.blur === "function") {
      try {
        el.blur();
      } catch (_) {
      }
    }
    if (options.clearPressStyle) _clearPress(el);
    const modalOwnsFocus = typeof isConfirmOpen === "function" && isConfirmOpen();
    if (!modalOwnsFocus && options.refocusComposer !== false && typeof refocusComposerAfterAction === "function") {
      refocusComposerAfterAction({
        preventScroll: options.preventScroll !== false,
        defer: !!options.defer
      });
    }
  }
  function bindPressable2(el, opts) {
    if (!el || !opts || typeof opts.onActivate !== "function") return null;
    if (el.dataset && el.dataset.pressableBound === "1") return null;
    if (el.dataset) el.dataset.pressableBound = "1";
    const onActivate = opts.onActivate;
    const options = {
      refocusComposer: opts.refocusComposer !== false,
      preventFocusTheft: !!opts.preventFocusTheft,
      preventScroll: opts.preventScroll !== false,
      defer: !!opts.defer,
      clearPressStyle: !!opts.clearPressStyle
    };
    const teardowns = [];
    if (options.preventFocusTheft) {
      const pointerdownHandler = (e) => {
        if (typeof e.button === "number" && e.button !== 0) return;
        e.preventDefault();
      };
      el.addEventListener("pointerdown", pointerdownHandler);
      teardowns.push(() => el.removeEventListener("pointerdown", pointerdownHandler));
    }
    const clickHandler = (e) => {
      try {
        onActivate(e);
      } finally {
        _afterActivate(el, options);
      }
    };
    el.addEventListener("click", clickHandler);
    teardowns.push(() => el.removeEventListener("click", clickHandler));
    if (!_isNativeButton(el)) {
      const keydownHandler = (e) => {
        if (e.key !== "Enter" && e.key !== " ") return;
        e.preventDefault();
        try {
          onActivate(e);
        } finally {
          _afterActivate(el, options);
        }
      };
      el.addEventListener("keydown", keydownHandler);
      teardowns.push(() => el.removeEventListener("keydown", keydownHandler));
    }
    return {
      dispose: () => {
        teardowns.forEach((fn) => {
          try {
            fn();
          } catch (_) {
          }
        });
        teardowns.length = 0;
        if (el.dataset) delete el.dataset.pressableBound;
      }
    };
  }
  return bindPressable2;
})(typeof window !== "undefined" ? window : globalThis);

// app/static/js/ui/ui_dismissible.js
var DarklabDismissible = (function(global) {
  "use strict";
  const LEVEL_PRIORITY = { modal: 3, sheet: 2, panel: 1 };
  const _registry = global.__darklabDismissibleRegistry || [];
  global.__darklabDismissibleRegistry = _registry;
  function _normalizeCloseButtons(input) {
    if (!input) return [];
    if (Array.isArray(input)) return input.filter(Boolean);
    return [input];
  }
  function bindDismissible2(el, opts) {
    if (!el || !opts) return null;
    if (el.dataset && el.dataset.dismissibleBound === "1") return null;
    if (!(opts.level in LEVEL_PRIORITY)) return null;
    if (typeof opts.onClose !== "function") return null;
    const level = opts.level;
    const isOpenFn = typeof opts.isOpen === "function" ? opts.isOpen : () => false;
    const onCloseFn = opts.onClose;
    const backdropEl = opts.backdropEl === void 0 ? el : opts.backdropEl;
    const closeOnBackdrop = opts.closeOnBackdrop !== false && backdropEl !== null;
    const closeButtons = _normalizeCloseButtons(opts.closeButtons);
    if (el.dataset) el.dataset.dismissibleBound = "1";
    const teardowns = [];
    const pressable = typeof bindPressable === "function" ? bindPressable : null;
    if (closeOnBackdrop && backdropEl && typeof backdropEl.addEventListener === "function") {
      const backdropHandler = (e) => {
        if (e.target !== backdropEl) return;
        if (!isOpenFn()) return;
        onCloseFn();
      };
      backdropEl.addEventListener("click", backdropHandler);
      teardowns.push(() => backdropEl.removeEventListener("click", backdropHandler));
    }
    closeButtons.forEach((btn) => {
      if (!btn || typeof btn.addEventListener !== "function") return;
      const alreadyPressable = btn.dataset && btn.dataset.pressableBound === "1";
      if (!alreadyPressable && pressable) {
        const handle = pressable(btn, {
          refocusComposer: false,
          onActivate: () => {
            if (isOpenFn()) onCloseFn();
          }
        });
        if (handle && typeof handle.dispose === "function") {
          teardowns.push(() => handle.dispose());
        }
      } else {
        const clickHandler = () => {
          if (isOpenFn()) onCloseFn();
        };
        btn.addEventListener("click", clickHandler);
        teardowns.push(() => btn.removeEventListener("click", clickHandler));
      }
    });
    const entry = { el, level, isOpen: isOpenFn, close: onCloseFn };
    _registry.push(entry);
    return {
      isOpen: () => isOpenFn(),
      close: () => {
        if (isOpenFn()) onCloseFn();
      },
      dispose: () => {
        const idx = _registry.indexOf(entry);
        if (idx >= 0) _registry.splice(idx, 1);
        if (el.dataset) delete el.dataset.dismissibleBound;
        teardowns.forEach((fn) => {
          try {
            fn();
          } catch (_) {
          }
        });
        teardowns.length = 0;
      }
    };
  }
  function closeTopmostDismissible2() {
    let best = null;
    let bestPriority = -1;
    let bestIdx = -1;
    for (let i = 0; i < _registry.length; i += 1) {
      const entry = _registry[i];
      if (!entry.isOpen()) continue;
      const pri = LEVEL_PRIORITY[entry.level] || 0;
      if (pri > bestPriority || pri === bestPriority && i > bestIdx) {
        best = entry;
        bestPriority = pri;
        bestIdx = i;
      }
    }
    if (!best) return false;
    best.close();
    return true;
  }
  const api = Object.freeze({
    bindDismissible: bindDismissible2,
    closeTopmostDismissible: closeTopmostDismissible2
  });
  return api;
})(typeof window !== "undefined" ? window : globalThis);
var { bindDismissible, closeTopmostDismissible } = DarklabDismissible;

export {
  bindDismissible,
  closeTopmostDismissible,
  bindMobileSheet,
  closeActionSheet,
  openActionSheet,
  bindFocusTrap,
  showConfirm,
  isConfirmOpen,
  bindPressable
};
