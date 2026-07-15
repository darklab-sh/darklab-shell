// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Neutral Welcome boundary for eager modules that should not import welcome.js.

let cancelWelcomeHandler = null;
let requestWelcomeSettleHandler = null;
let welcomeOwnsTabHandler = null;

function setWelcomeHandlers(handlers = {}) {
  if (typeof handlers.cancelWelcome === 'function') cancelWelcomeHandler = handlers.cancelWelcome;
  if (typeof handlers.requestWelcomeSettle === 'function') requestWelcomeSettleHandler = handlers.requestWelcomeSettle;
  if (typeof handlers.welcomeOwnsTab === 'function') welcomeOwnsTabHandler = handlers.welcomeOwnsTab;
}

function cancelWelcome(...args) {
  return typeof cancelWelcomeHandler === 'function'
    ? cancelWelcomeHandler(...args)
    : undefined;
}

function welcomeOwnsTab(...args) {
  return typeof welcomeOwnsTabHandler === 'function'
    ? !!welcomeOwnsTabHandler(...args)
    : false;
}

function requestWelcomeSettle(...args) {
  return typeof requestWelcomeSettleHandler === 'function'
    ? requestWelcomeSettleHandler(...args)
    : undefined;
}

export {
  cancelWelcome,
  requestWelcomeSettle,
  setWelcomeHandlers,
  welcomeOwnsTab,
};
