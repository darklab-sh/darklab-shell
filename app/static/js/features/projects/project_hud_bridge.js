// Neutral shell-HUD boundary for preference-driven HUD refreshes.

let renderHudClockHandler = null;

function setProjectHudHandlers(handlers = {}) {
  if (typeof handlers.renderHudClock === 'function') {
    renderHudClockHandler = handlers.renderHudClock;
  }
}

function renderHudClock(...args) {
  return typeof renderHudClockHandler === 'function'
    ? renderHudClockHandler(...args)
    : undefined;
}

export {
  renderHudClock,
  setProjectHudHandlers,
};
