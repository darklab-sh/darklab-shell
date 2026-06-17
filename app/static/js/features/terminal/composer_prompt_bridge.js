// Neutral composer prompt boundary for Preferences -> app prompt updates.

const composerPromptHandlers = {
  getComposerPromptMode: null,
  hidePromptUsernameSavedIndicator: null,
  setComposerPromptMode: null,
  showPromptUsernameSavedIndicator: null,
  syncShellPrompt: null,
};

function setComposerPromptHandlers(handlers = {}) {
  Object.keys(composerPromptHandlers).forEach((name) => {
    if (typeof handlers[name] === 'function') composerPromptHandlers[name] = handlers[name];
  });
}

function hasComposerPromptHandler(name) {
  return typeof composerPromptHandlers[name] === 'function';
}

function getComposerPromptMode() {
  return typeof composerPromptHandlers.getComposerPromptMode === 'function'
    ? composerPromptHandlers.getComposerPromptMode()
    : null;
}

function hidePromptUsernameSavedIndicator(...args) {
  return typeof composerPromptHandlers.hidePromptUsernameSavedIndicator === 'function'
    ? composerPromptHandlers.hidePromptUsernameSavedIndicator(...args)
    : undefined;
}

function showPromptUsernameSavedIndicator(...args) {
  return typeof composerPromptHandlers.showPromptUsernameSavedIndicator === 'function'
    ? composerPromptHandlers.showPromptUsernameSavedIndicator(...args)
    : undefined;
}

function setComposerPromptMode(...args) {
  return typeof composerPromptHandlers.setComposerPromptMode === 'function'
    ? composerPromptHandlers.setComposerPromptMode(...args)
    : undefined;
}

function syncShellPrompt(...args) {
  return typeof composerPromptHandlers.syncShellPrompt === 'function'
    ? composerPromptHandlers.syncShellPrompt(...args)
    : undefined;
}

export {
  getComposerPromptMode,
  hasComposerPromptHandler,
  hidePromptUsernameSavedIndicator,
  setComposerPromptHandlers,
  setComposerPromptMode,
  showPromptUsernameSavedIndicator,
  syncShellPrompt,
};
