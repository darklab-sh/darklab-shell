// Single imperative primitive for modal confirmations in the shell.
//
// Every destructive or mode-switching confirmation (kill, history-delete,
// history-clear, share-redaction, session-token set/migrate) resolves through
// this helper. Previously each one hand-rolled its own markup, show/hide
// helpers, bindDismissible registration, bindMobileSheet registration,
// affirmative-button listener, and composer-refocus dance; now they share a
// single pre-minted `#confirm-host` element and a declarative call shape.
//
// Callers compose the modal declaratively via a single call:
//
//   const choice = await showConfirm({
//     body: { text: 'Kill the running process?', note: 'Sends SIGTERM.' },
//     tone: 'danger',
//     actions: [
//       { id: 'cancel',  label: 'Cancel', role: 'cancel' },
//       { id: 'confirm', label: '■ Kill', role: 'primary', tone: 'danger' },
//     ],
//   });
//
// Resolves with:
//   - actions[i].id — when that action is activated
//   - null          — when the user cancels (Escape / backdrop / mobile
//                     sheet drag-down / the role:'cancel' action)
//
// Semantics:
// - One confirm at a time. A second call while open is rejected; the
//   shell never stacks confirms today, and the UI sequence that would
//   cause it (clicking through the backdrop-protected area) is not
//   reachable by the user.
// - Default focus lands on the role:'cancel' button. Browser native
//   Enter-activates-focused-button then makes Enter === cancel — a safe,
//   macOS/web convention. Pass `defaultFocus` (an action id or a DOM
//   Node inside the content slot) to override; explicit defaultFocus
//   wins over the cancel fallback so dialogs with form inputs can land
//   focus directly on the input.
// - Stacks action buttons vertically when the viewport is <=480px OR the
//   action count is >=3, via `.modal-actions-stacked`. A matchMedia
//   listener keeps the class reactive to resize while the modal is open.
// - Composes with bindDismissible ('modal' level) for Escape + backdrop
//   dismissal and with bindMobileSheet for the drag-down-to-close handle.
// - Optional `content` slot (Node | array of Nodes) renders arbitrary
//   markup between the body and the action row — for checkboxes, text
//   inputs, and any other caller-managed form controls. The primitive
//   does not inspect or validate content; the caller owns event wiring.
// - Optional `action.onActivate` lets a caller gate the close. It is
//   invoked when the action is clicked; returning (or resolving to)
//   a falsy value keeps the modal open so validation errors can stay
//   on screen. Any other return closes and resolves with the action id.
(function (global) {
  'use strict';

  const STACKED_BREAKPOINT = 480;

  let _activeState = null; // { resolve, dismissibleHandle, mqList }
  let _host = null;
  let _card = null;
  let _bodyEl = null;
  let _contentEl = null;
  let _actionsEl = null;

  function _getHost() {
    if (_host) return _host;
    _host = document.getElementById('confirm-host');
    if (!_host) return null;
    _card = _host.querySelector('[data-confirm-card]');
    _bodyEl = _host.querySelector('[data-confirm-body]');
    _contentEl = _host.querySelector('[data-confirm-content]');
    _actionsEl = _host.querySelector('[data-confirm-actions]');
    return _host;
  }

  function _isOpen() {
    return !!_activeState;
  }

  function _classForAction(action) {
    const role = action.role || 'secondary';
    const tone = action.tone || null;
    let cls = 'btn';
    if (role === 'primary')       cls += ' btn-primary';
    else if (role === 'ghost')    cls += ' btn-ghost';
    else                          cls += ' btn-secondary'; // cancel, secondary, default
    if (tone === 'danger')        cls += ' btn-danger';
    else if (tone === 'warning')  cls += ' btn-warning';
    return cls;
  }

  function _renderBody(target, body) {
    target.innerHTML = '';
    if (body === undefined || body === null || body === '') return;
    if (typeof body === 'string') {
      target.textContent = body;
      return;
    }
    if (body instanceof Node) {
      target.appendChild(body);
      return;
    }
    if (typeof body === 'object' && (typeof body.text === 'string' || typeof body.note === 'string')) {
      if (typeof body.text === 'string' && body.text !== '') {
        target.appendChild(document.createTextNode(body.text));
      }
      if (typeof body.note === 'string' && body.note !== '') {
        if (target.childNodes.length > 0) target.appendChild(document.createElement('br'));
        const note = document.createElement('span');
        note.className = 'modal-copy-note';
        note.textContent = body.note;
        target.appendChild(note);
      }
      return;
    }
    target.textContent = String(body);
  }

  function _renderContent(target, content) {
    target.innerHTML = '';
    if (content === undefined || content === null) return;
    const nodes = Array.isArray(content) ? content : [content];
    nodes.forEach((node) => {
      if (node instanceof Node) target.appendChild(node);
    });
  }

  function _shouldStack(actionCount) {
    if (actionCount >= 3) return true;
    if (typeof window === 'undefined' || !window.matchMedia) return false;
    return window.matchMedia(`(max-width: ${STACKED_BREAKPOINT}px)`).matches;
  }

  function _applyStacking(actionCount) {
    if (!_actionsEl) return;
    _actionsEl.classList.toggle('modal-actions-stacked', _shouldStack(actionCount));
  }

  function _cleanup(state) {
    if (!_host) return;
    if (state && state.mqList && typeof state.mqList.remove === 'function') state.mqList.remove();
    if (state && state.focusTrapHandle && typeof state.focusTrapHandle.dispose === 'function') {
      state.focusTrapHandle.dispose();
    }
    if (state && state.dismissibleHandle && typeof state.dismissibleHandle.dispose === 'function') {
      state.dismissibleHandle.dispose();
    }
    if (typeof global.hideModalOverlay === 'function') {
      global.hideModalOverlay(_host);
    } else if (_host.style) {
      _host.style.display = 'none';
    }
    _host.classList.add('u-hidden');
    if (_card) _card.classList.remove('modal-card-danger', 'modal-card-warning');
    if (_actionsEl) {
      _actionsEl.innerHTML = '';
      _actionsEl.classList.remove('modal-actions-stacked');
    }
    if (_bodyEl) _bodyEl.innerHTML = '';
    if (_contentEl) _contentEl.innerHTML = '';
  }

  function _resolveWith(value) {
    if (!_activeState) return;
    const state = _activeState;
    _activeState = null;
    try {
      _cleanup(state);
    } finally {
      if (typeof global.refocusComposerAfterAction === 'function') {
        global.refocusComposerAfterAction({ defer: true });
      }
      state.resolve(value);
    }
  }

  function showConfirm(opts) {
    const host = _getHost();
    if (!host) return Promise.reject(new Error('showConfirm: #confirm-host not present'));
    if (_isOpen()) return Promise.reject(new Error('showConfirm: another confirm is already open'));

    const body = opts && opts.body !== undefined ? opts.body : '';
    const content = opts && opts.content !== undefined ? opts.content : null;
    const tone = opts && opts.tone ? opts.tone : null; // 'danger' | 'warning' | null
    const actions = opts && Array.isArray(opts.actions) ? opts.actions.filter(a => a && a.id) : [];
    if (actions.length === 0) return Promise.reject(new Error('showConfirm: actions required'));

    _renderBody(_bodyEl, body);
    if (_contentEl) _renderContent(_contentEl, content);
    _card.classList.remove('modal-card-danger', 'modal-card-warning');
    if (tone === 'danger') _card.classList.add('modal-card-danger');
    else if (tone === 'warning') _card.classList.add('modal-card-warning');

    // Build action buttons. An action with onActivate is gated: the
    // callback runs first, and the primitive only closes if the return
    // (or resolved Promise value) is truthy.
    _actionsEl.innerHTML = '';
    const buttons = [];
    actions.forEach((action) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = _classForAction(action);
      btn.textContent = action.label || '';
      btn.dataset.confirmActionId = action.id;
      if (action.role === 'cancel') btn.dataset.confirmRole = 'cancel';
      btn.addEventListener('click', async () => {
        if (typeof action.onActivate === 'function') {
          let result;
          try { result = action.onActivate(); }
          catch (_) { return; }
          if (result && typeof result.then === 'function') {
            try { result = await result; }
            catch (_) { return; }
          }
          if (!result) return; // keep the modal open
        }
        _resolveWith(action.id);
      });
      _actionsEl.appendChild(btn);
      buttons.push({ btn, action });
    });
    _applyStacking(actions.length);

    // Show the host.
    host.classList.remove('u-hidden');
    if (typeof global.showModalOverlay === 'function') {
      global.showModalOverlay(host, 'flex');
    } else if (host.style) {
      host.style.display = 'flex';
    }

    // Install the promise before binding Escape / backdrop, so handlers
    // that read _isOpen() at close time see the open state.
    let resolveFn;
    const promise = new Promise((resolve) => { resolveFn = resolve; });

    const state = {
      resolve: resolveFn,
      dismissibleHandle: null,
      focusTrapHandle: null,
      mqList: null,
    };
    _activeState = state;

    // Focus trap: keep Tab cycling inside the card while the modal is open;
    // otherwise Tab falls through to the document and starts cycling into
    // rail / tab / HUD buttons behind the backdrop.
    if (typeof global.bindFocusTrap === 'function' && _card) {
      state.focusTrapHandle = global.bindFocusTrap(_card);
    }

    // Escape + backdrop via bindDismissible.
    if (typeof global.bindDismissible === 'function') {
      state.dismissibleHandle = global.bindDismissible(host, {
        level: 'modal',
        isOpen: _isOpen,
        onClose: () => _resolveWith(null),
        closeOnBackdrop: true,
      });
    }
    // Mobile sheet drag handle. bindMobileSheet is idempotent; safe to
    // call on every open — the injected grab element persists.
    if (typeof global.bindMobileSheet === 'function' && _card) {
      global.bindMobileSheet(_card, { onClose: () => _resolveWith(null) });
    }

    // Keep stacking reactive while the modal is open.
    if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
      const mq = window.matchMedia(`(max-width: ${STACKED_BREAKPOINT}px)`);
      const handler = () => _applyStacking(actions.length);
      if (typeof mq.addEventListener === 'function') {
        mq.addEventListener('change', handler);
        state.mqList = { remove: () => mq.removeEventListener('change', handler) };
      } else if (typeof mq.addListener === 'function') {
        mq.addListener(handler);
        state.mqList = { remove: () => mq.removeListener(handler) };
      }
    }

    // Default focus precedence:
    //   1. explicit `defaultFocus` — Node wins literally; a string looks
    //      up an action id. Explicit callers (e.g. modals with a form
    //      input) need to override the cancel fallback.
    //   2. role:'cancel' button — the safe default for confirmation
    //      dialogs so Enter activates cancel.
    //   3. first button — last resort when neither cancel nor default
    //      focus applies.
    let focusTarget = null;
    if (opts.defaultFocus instanceof Node) {
      focusTarget = opts.defaultFocus;
    } else if (typeof opts.defaultFocus === 'string' && opts.defaultFocus) {
      const explicit = buttons.find(({ action }) => action.id === opts.defaultFocus);
      if (explicit) focusTarget = explicit.btn;
    }
    if (!focusTarget) {
      const cancel = buttons.find(({ action }) => action.role === 'cancel');
      if (cancel) focusTarget = cancel.btn;
    }
    if (!focusTarget && buttons.length) focusTarget = buttons[0].btn;
    if (focusTarget && typeof focusTarget.focus === 'function') {
      try { focusTarget.focus(); } catch (_) { /* non-critical */ }
    }

    return promise;
  }

  // Programmatic dismissal hook — resolves the open confirm with null.
  // Used by teardown paths (e.g., tab closed while its confirm was open).
  function cancelConfirm() {
    _resolveWith(null);
  }

  function isConfirmOpen() {
    return _isOpen();
  }

  global.showConfirm = showConfirm;
  global.cancelConfirm = cancelConfirm;
  global.isConfirmOpen = isConfirmOpen;
})(typeof window !== 'undefined' ? window : globalThis);
