// Neutral Welcome boundary for eager modules that should not import welcome.js.

let cancelWelcomeHandler = null;
let welcomeOwnsTabHandler = null;

function setWelcomeHandlers(handlers = {}) {
  if (typeof handlers.cancelWelcome === 'function') cancelWelcomeHandler = handlers.cancelWelcome;
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

export {
  cancelWelcome,
  setWelcomeHandlers,
  welcomeOwnsTab,
};
