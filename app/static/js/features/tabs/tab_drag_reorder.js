// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { tabsBar as importedTabsBar } from '../../core/dom.js';
import { getActiveTabId as importedGetActiveTabId } from '../../core/state.js';
import {
  ensureActiveTabVisible as importedEnsureActiveTabVisible,
  syncTabOrderFromDom as importedSyncTabOrderFromDom,
  updateTabScrollButtons as importedUpdateTabScrollButtons,
} from '../../tabs_bridge.js';
import { refocusComposerAfterAction as importedRefocusComposerAfterAction } from '../../ui/ui_helpers.js';

const TAB_DRAG_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

let _tabDragSuppressClickUntil = 0;
let _touchDragState = null;
const _TOUCH_TAB_DRAG_THRESHOLD = 14;
const _TOUCH_TAB_DRAG_HOLD_MS = 180;
const _POINTER_TAB_DRAG_THRESHOLD = 6;

function _tabDragTabsBar() {
  return (typeof importedTabsBar !== 'undefined' && importedTabsBar)
    || TAB_DRAG_GLOBAL.tabsBar
    || null;
}

function _tabDragActiveTabId() {
  if (typeof importedGetActiveTabId !== 'undefined' && typeof importedGetActiveTabId === 'function') {
    return importedGetActiveTabId();
  }
  return TAB_DRAG_GLOBAL.activeTabId ?? null;
}

function _tabDragUpdateTabScrollButtons() {
  const update = (typeof importedUpdateTabScrollButtons !== 'undefined' && importedUpdateTabScrollButtons)
    || (typeof TAB_DRAG_GLOBAL.updateTabScrollButtons === 'function'
      ? TAB_DRAG_GLOBAL.updateTabScrollButtons
      : null);
  if (typeof update === 'function') update();
}

function _tabDragSyncTabOrderFromDom() {
  const sync = (typeof importedSyncTabOrderFromDom !== 'undefined' && importedSyncTabOrderFromDom)
    || (typeof TAB_DRAG_GLOBAL.syncTabOrderFromDom === 'function'
      ? TAB_DRAG_GLOBAL.syncTabOrderFromDom
      : null);
  if (typeof sync === 'function') sync();
}

function _tabDragEnsureActiveTabVisible(tabId) {
  const ensureVisible = (typeof importedEnsureActiveTabVisible !== 'undefined' && importedEnsureActiveTabVisible)
    || (typeof TAB_DRAG_GLOBAL.ensureActiveTabVisible === 'function'
      ? TAB_DRAG_GLOBAL.ensureActiveTabVisible
      : null);
  if (typeof ensureVisible === 'function') ensureVisible(tabId);
}

function _tabDragRefocusComposerAfterAction() {
  const refocus = (typeof importedRefocusComposerAfterAction !== 'undefined' && importedRefocusComposerAfterAction)
    || (typeof TAB_DRAG_GLOBAL.refocusComposerAfterAction === 'function'
      ? TAB_DRAG_GLOBAL.refocusComposerAfterAction
      : null);
  if (typeof refocus === 'function') refocus();
}

function _syncTabDraggable(tab) {
  if (!tab) return;
  tab.setAttribute('draggable', 'false');
}

function _clearTabDropIndicators() {
  const bar = _tabDragTabsBar();
  if (!bar) return;
  bar.querySelectorAll('.tab-drop-before, .tab-drop-after').forEach(node => {
    node.classList.remove('tab-drop-before', 'tab-drop-after');
  });
}

function _tabFromClientX(clientX, excludeId = null) {
  const bar = _tabDragTabsBar();
  if (!bar) return null;
  const nodes = [...bar.querySelectorAll('.tab')];
  return nodes.find(node => {
    if (!node || node.dataset.id === excludeId) return false;
    const rect = node.getBoundingClientRect();
    return clientX >= rect.left && clientX <= rect.right;
  }) || null;
}

function _edgeTabFromClientX(clientX, excludeId = null) {
  const bar = _tabDragTabsBar();
  if (!bar) return null;
  const nodes = [...bar.querySelectorAll('.tab')].filter(node => node && node.dataset.id !== excludeId);
  if (!nodes.length) return null;
  const first = nodes[0];
  const last = nodes[nodes.length - 1];
  const firstRect = first.getBoundingClientRect();
  const lastRect = last.getBoundingClientRect();
  if (clientX < firstRect.left) return { target: first, after: false };
  if (clientX > lastRect.right) return { target: last, after: true };
  return null;
}

function _reorderDraggedTab(dragged, target, clientX) {
  const bar = _tabDragTabsBar();
  if (!dragged || !target || !bar || dragged === target) return false;
  const rect = target.getBoundingClientRect();
  const after = clientX > rect.left + (rect.width / 2);
  const noChange = after
    ? target.nextSibling === dragged
    : target === dragged.nextSibling;
  if (noChange) {
    _clearTabDropIndicators();
    return false;
  }
  _clearTabDropIndicators();
  target.classList.add(after ? 'tab-drop-after' : 'tab-drop-before');
  if (after) {
    if (target.nextSibling !== dragged) bar.insertBefore(dragged, target.nextSibling);
  } else if (target !== dragged.nextSibling) {
    bar.insertBefore(dragged, target);
  }
  return true;
}

function _touchDragAutoScroll(clientX) {
  const bar = _tabDragTabsBar();
  if (!bar || typeof bar.scrollBy !== 'function') return;
  const rect = bar.getBoundingClientRect();
  const edge = 36;
  if (clientX <= rect.left + edge) bar.scrollBy({ left: -18, behavior: 'auto' });
  else if (clientX >= rect.right - edge) bar.scrollBy({ left: 18, behavior: 'auto' });
}

function _getTrackedTouchPoint(e, touchId = null) {
  const pools = [];
  if (e && e.touches) pools.push(e.touches);
  if (e && e.changedTouches) pools.push(e.changedTouches);
  for (const pool of pools) {
    for (const touch of pool) {
      if (touchId === null || touch.identifier === touchId) return touch;
    }
  }
  return null;
}

function _cleanupTouchDrag() {
  // Touch drag state spans document-level listeners, so cleanup has to fully
  // unwind everything even when the gesture is cancelled mid-drag.
  if (!_touchDragState) return;
  if (
    _touchDragState.tab
    && typeof _touchDragState.pointerId === 'number'
    && typeof _touchDragState.tab.releasePointerCapture === 'function'
  ) {
    try { _touchDragState.tab.releasePointerCapture(_touchDragState.pointerId); } catch (_) {}
  }
  document.removeEventListener('pointermove', _onTouchDragMove);
  document.removeEventListener('pointerup', _onTouchDragEnd);
  document.removeEventListener('pointercancel', _onTouchDragEnd);
  document.removeEventListener('touchmove', _onTouchDragMove);
  document.removeEventListener('touchend', _onTouchDragEnd);
  document.removeEventListener('touchcancel', _onTouchDragEnd);
  _clearTabDropIndicators();
  const bar = _tabDragTabsBar();
  bar?.classList.remove('tabs-bar-touch-sorting');
  bar?.classList.remove('tabs-bar-desktop-sorting');
  _touchDragState.tab.classList.remove('tab-dragging', 'tab-touch-dragging', 'tab-pointer-dragging');
  if (_touchDragState.holdTimer) clearTimeout(_touchDragState.holdTimer);
  _touchDragState = null;
}

function _onTouchDragMove(e) {
  if (!_touchDragState) return;
  let clientX;
  let clientY;
  if (_touchDragState.source === 'touch') {
    const point = _getTrackedTouchPoint(e, _touchDragState.touchId);
    if (!point) return;
    clientX = point.clientX;
    clientY = point.clientY;
  } else {
    if (e.pointerId !== _touchDragState.pointerId) return;
    clientX = e.clientX;
    clientY = e.clientY;
  }
  const dx = clientX - _touchDragState.startX;
  const dy = clientY - _touchDragState.startY;
  if (!_touchDragState.active) {
    if (_touchDragState.source === 'touch') {
      if (Math.abs(dx) >= _TOUCH_TAB_DRAG_THRESHOLD || Math.abs(dy) >= _TOUCH_TAB_DRAG_THRESHOLD) {
        if (_touchDragState.holdTimer) {
          clearTimeout(_touchDragState.holdTimer);
          _touchDragState.holdTimer = null;
        }
        _cleanupTouchDrag();
      }
      return;
    }
    if (Math.abs(dx) < _POINTER_TAB_DRAG_THRESHOLD && Math.abs(dy) < _POINTER_TAB_DRAG_THRESHOLD) return;
    _touchDragState.active = true;
    if (typeof e.preventDefault === 'function') e.preventDefault();
    if (typeof e.stopPropagation === 'function') e.stopPropagation();
    _tabDragTabsBar()?.classList.add('tabs-bar-desktop-sorting');
    _touchDragState.tab.classList.add('tab-dragging', 'tab-pointer-dragging');
  }
  if (typeof e.preventDefault === 'function') e.preventDefault();
  if (typeof e.stopPropagation === 'function') e.stopPropagation();
  const dragged = _touchDragState.tab;
  const target = _tabFromClientX(clientX, _touchDragState.id);
  const edgeDrop = target ? null : _edgeTabFromClientX(clientX, _touchDragState.id);
  if (target) {
    const changed = _reorderDraggedTab(dragged, target, clientX);
    if (changed) _touchDragState.moved = true;
  } else if (edgeDrop && edgeDrop.target !== dragged) {
    const bar = _tabDragTabsBar();
    const firstTab = bar ? bar.querySelector('.tab') : null;
    const lastTab = bar ? bar.querySelector('.tab:last-of-type') : null;
    const noChange = (!edgeDrop.after && firstTab === dragged) || (edgeDrop.after && lastTab === dragged);
    if (noChange) {
      _clearTabDropIndicators();
      _tabDragUpdateTabScrollButtons();
      return;
    }
    _clearTabDropIndicators();
    edgeDrop.target.classList.add(edgeDrop.after ? 'tab-drop-after' : 'tab-drop-before');
    if (edgeDrop.after) {
      bar.appendChild(dragged);
    } else if (bar) {
      bar.insertBefore(dragged, bar.querySelector('.tab'));
    }
    _touchDragState.moved = true;
  } else {
    _clearTabDropIndicators();
  }
  _touchDragAutoScroll(clientX);
  _tabDragUpdateTabScrollButtons();
}

function _onTouchDragEnd(e) {
  if (!_touchDragState) return;
  if (_touchDragState.source === 'touch') {
    if (!_getTrackedTouchPoint(e, _touchDragState.touchId) && e.type !== 'touchcancel') return;
  } else if (e.pointerId !== _touchDragState.pointerId) {
    return;
  }
  const state = _touchDragState;
  const moved = state.active && state.moved;
  _cleanupTouchDrag();
  _syncTabDraggable(state.tab);
  if (!moved) return;
  _tabDragSyncTabOrderFromDom();
  _tabDragUpdateTabScrollButtons();
  const currentActiveTabId = _tabDragActiveTabId();
  _tabDragEnsureActiveTabVisible(currentActiveTabId);
  _tabDragSuppressClickUntil = Date.now() + (state.source === 'touch' ? 220 : 140);
  if (typeof window !== 'undefined')  if (state.id === currentActiveTabId) _tabDragRefocusComposerAfterAction();
}

function _startTouchTabDrag(tab, id, e) {
  if (!e) return;
  const isTouchEvent = e.type === 'touchstart';
  if (!isTouchEvent && e.pointerType === 'touch') return;
  if (!isTouchEvent && e.pointerType !== 'mouse') return;
  if (!isTouchEvent && typeof e.button === 'number' && e.button !== 0) return;
  if (e.target && e.target.closest && e.target.closest('.tab-close')) return;
  _syncTabDraggable(tab);
  _cleanupTouchDrag();
  const point = isTouchEvent ? _getTrackedTouchPoint(e) : e;
  if (!point) return;
  const pointerId = !isTouchEvent && typeof e.pointerId === 'number' ? e.pointerId : null;
  if (pointerId !== null && typeof tab.setPointerCapture === 'function') {
    try { tab.setPointerCapture(e.pointerId); } catch (_) {}
  }
  _touchDragState = {
    id,
    tab,
    source: isTouchEvent ? 'touch' : 'pointer',
    pointerId,
    touchId: isTouchEvent && typeof point.identifier === 'number' ? point.identifier : null,
    startX: point.clientX,
    startY: point.clientY,
    active: false,
    moved: false,
    holdTimer: null,
  };
  if (isTouchEvent) {
    _touchDragState.holdTimer = setTimeout(() => {
      if (!_touchDragState || _touchDragState.id !== id || _touchDragState.tab !== tab) return;
      _touchDragState.holdTimer = null;
      _touchDragState.active = true;
      _tabDragTabsBar()?.classList.add('tabs-bar-touch-sorting');
      _touchDragState.tab.classList.add('tab-dragging', 'tab-touch-dragging');
    }, _TOUCH_TAB_DRAG_HOLD_MS);
  }
  if (isTouchEvent) {
    document.addEventListener('touchmove', _onTouchDragMove, { passive: false });
    document.addEventListener('touchend', _onTouchDragEnd);
    document.addEventListener('touchcancel', _onTouchDragEnd);
  } else {
    document.addEventListener('pointermove', _onTouchDragMove, { passive: false });
    document.addEventListener('pointerup', _onTouchDragEnd);
    document.addEventListener('pointercancel', _onTouchDragEnd);
  }
}

function bindTabDragReorder(tab, id) {
  if (!tab) return;
  _syncTabDraggable(tab);
  tab.addEventListener('pointerdown', e => _startTouchTabDrag(tab, id, e));
  tab.addEventListener('touchstart', e => _startTouchTabDrag(tab, id, e), { passive: false });
}

function tabDragSuppressClickUntil() {
  return _tabDragSuppressClickUntil;
}

export {
  _POINTER_TAB_DRAG_THRESHOLD,
  _TOUCH_TAB_DRAG_HOLD_MS,
  _TOUCH_TAB_DRAG_THRESHOLD,
  _cleanupTouchDrag,
  _clearTabDropIndicators,
  _edgeTabFromClientX,
  _getTrackedTouchPoint,
  _onTouchDragEnd,
  _onTouchDragMove,
  _reorderDraggedTab,
  _startTouchTabDrag,
  _syncTabDraggable,
  _tabFromClientX,
  _touchDragAutoScroll,
  bindTabDragReorder,
  tabDragSuppressClickUntil,
};
