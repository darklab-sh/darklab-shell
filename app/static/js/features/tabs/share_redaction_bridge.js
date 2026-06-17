// Neutral share-redaction prompt boundary for tab export actions.

let confirmPermalinkRedactionChoiceHandler = null;

function setShareRedactionHandlers(handlers = {}) {
  if (typeof handlers.confirmPermalinkRedactionChoice === 'function') {
    confirmPermalinkRedactionChoiceHandler = handlers.confirmPermalinkRedactionChoice;
  }
}

function hasShareRedactionHandler(name) {
  return name === 'confirmPermalinkRedactionChoice'
    && typeof confirmPermalinkRedactionChoiceHandler === 'function';
}

function confirmPermalinkRedactionChoice(...args) {
  return typeof confirmPermalinkRedactionChoiceHandler === 'function'
    ? confirmPermalinkRedactionChoiceHandler(...args)
    : undefined;
}

export {
  confirmPermalinkRedactionChoice,
  hasShareRedactionHandler,
  setShareRedactionHandlers,
};
