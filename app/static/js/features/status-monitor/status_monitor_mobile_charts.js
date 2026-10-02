// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { bindPressable } from '../../ui/ui_pressable.js';
import { bindOutsideClickClose } from '../../ui/ui_outside_click.js';

// One controller per monitor; WeakMap entries follow the rendered cards.
// Desktop events pass through to the existing chart handlers.
function createStatusMonitorMobileCharts({ monitor, isMobile, hidePopover }) {
  const panels = new WeakMap();
  let selected = null;
  let gesture = null;
  let completedTap = null;

  function dismiss() {
    if (!selected) return;
    hidePopover(selected.panel);
    selected.button.classList.add('u-hidden');
    selected.target.setAttribute('aria-expanded', 'false');
    selected = null;
  }

  function reset() {
    dismiss();
    gesture = null;
    completedTap = null;
  }

  function targetFor(event) {
    const panel = event.target.closest?.('.status-monitor-visual-card');
    const config = panels.get(panel);
    if (!config) return null;
    const target = event.target.closest(config.targetSelector);
    return target && panel.contains(target) ? { panel, config, target } : null;
  }

  function pressTarget(event) {
    return event.target.closest?.('.status-monitor-chart-action') || targetFor(event)?.target;
  }

  function cancelMovedPress(event) {
    if (!gesture || gesture.id !== event.pointerId) return;
    if (Math.hypot(event.clientX - gesture.x, event.clientY - gesture.y) > 8) {
      gesture.cancelled = true;
      dismiss();
    }
  }

  function acceptClick(event, target) {
    // Keyboard and assistive activation have no pointer gesture.
    if (event.detail === 0 && !event.pointerType) return true;
    const tap = completedTap;
    completedTap = null;
    return !!(tap && tap.target === target && tap.selection === selected);
  }

  function select({ panel, config, target }, keyboard = false) {
    const payload = config.resolve(target);
    if (!payload) return;
    dismiss();
    const { button, popover } = config;
    selected = { panel, target, button, payload, config };
    target.setAttribute('aria-expanded', 'true');
    button.classList.remove('u-hidden');
    popover.setAttribute('role', 'group');
    popover.setAttribute('aria-label', config.label === 'Open run' ? 'Run preview' : 'Command history preview');
    config.show(payload, target);
    if (keyboard) button.focus({ preventScroll: true });
  }

  monitor.addEventListener('pointerdown', event => {
    if (!isMobile()) return;
    completedTap = null;
    if (event.isPrimary === false || event.button !== 0) {
      if (gesture) gesture.cancelled = true;
      return;
    }
    gesture = {
      id: event.pointerId, x: event.clientX, y: event.clientY,
      target: pressTarget(event), selection: selected, cancelled: false,
    };
  }, true);
  monitor.addEventListener('pointermove', cancelMovedPress, { capture: true, passive: true });
  monitor.addEventListener('pointerup', event => {
    cancelMovedPress(event);
    if (!gesture || gesture.id !== event.pointerId) return;
    completedTap = !gesture.cancelled && gesture.target === pressTarget(event) ? gesture : null;
    gesture = null;
  }, true);
  monitor.addEventListener('pointercancel', () => {
    if (isMobile()) reset();
  }, true);

  monitor.addEventListener('click', event => {
    if (!isMobile()) return;
    const button = event.target.closest?.('.status-monitor-chart-action');
    if (button) {
      if (button !== selected?.button || !acceptClick(event, button)) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
      return;
    }
    const target = targetFor(event);
    if (target) {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (acceptClick(event, target.target)) select(target);
    } else if (!selected?.config.popover.contains(event.target)) {
      reset();
    }
  }, true);

  monitor.addEventListener('keydown', event => {
    if (!isMobile()) return;
    if (event.key === 'Escape' && selected) {
      const trigger = selected.target;
      event.preventDefault();
      event.stopPropagation();
      reset();
      trigger.focus({ preventScroll: true });
    } else if (event.key === 'Enter' || event.key === ' ') {
      const target = targetFor(event);
      if (!target) return;
      event.preventDefault();
      event.stopPropagation();
      select(target, true);
    }
  }, true);

  bindOutsideClickClose(monitor, {
    isOpen: () => isMobile() && !!selected,
    onClose: reset,
    capture: true,
  });
  document.addEventListener('scroll', event => {
    if (isMobile() && (monitor.contains(event.target) || event.target === document)) reset();
  }, { capture: true, passive: true });

  function register(panel, config) {
    const popover = panel.querySelector('.status-monitor-constellation-popover');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn btn-secondary status-monitor-chart-action u-hidden';
    button.textContent = config.label;
    bindPressable(button, {
      refocusComposer: false,
      onActivate: event => {
        event.preventDefault();
        event.stopPropagation();
        if (!isMobile() || selected?.button !== button) return;
        const { payload } = selected;
        reset();
        config.activate(payload);
      },
    });
    popover.appendChild(button);
    panels.set(panel, { ...config, popover, button });
  }

  return { register, reset };
}

export { createStatusMonitorMobileCharts };
