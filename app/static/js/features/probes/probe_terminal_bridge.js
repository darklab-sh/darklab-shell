// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Neutral boundary between the eager terminal and the lazy probe planner.

let probeTerminalHandler = null;

function setProbeTerminalHandler(handler) {
  if (typeof handler === 'function') probeTerminalHandler = handler;
}

function hasProbeTerminalHandler() {
  return typeof probeTerminalHandler === 'function';
}

function handleProbeTerminalCommand(...args) {
  return hasProbeTerminalHandler() ? probeTerminalHandler(...args) : false;
}

export {
  handleProbeTerminalCommand,
  hasProbeTerminalHandler,
  setProbeTerminalHandler,
};
