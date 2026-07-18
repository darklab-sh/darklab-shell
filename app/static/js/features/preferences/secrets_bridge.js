// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Neutral Options Secrets boundary for lazy callers and runtime consumers.

const secretsHandlers = {
  refreshOptionsSecrets: null,
  invalidateOptionsSecrets: null,
  openSecretEditor: null,
  openProviderStatusModal: null,
  closeProviderStatusModal: null,
  isProviderStatusModalOpen: null,
  deleteOptionsSecret: null,
  handleSecretCommand: null,
};

function setSecretsHandlers(handlers = {}) {
  Object.keys(secretsHandlers).forEach((name) => {
    if (typeof handlers[name] === 'function') secretsHandlers[name] = handlers[name];
  });
}

function hasSecretsHandler(name) {
  return typeof secretsHandlers[name] === 'function';
}

function refreshOptionsSecrets(...args) {
  return typeof secretsHandlers.refreshOptionsSecrets === 'function'
    ? secretsHandlers.refreshOptionsSecrets(...args)
    : undefined;
}

function invalidateOptionsSecrets(...args) {
  return typeof secretsHandlers.invalidateOptionsSecrets === 'function'
    ? secretsHandlers.invalidateOptionsSecrets(...args)
    : undefined;
}

function openSecretEditor(...args) {
  return typeof secretsHandlers.openSecretEditor === 'function'
    ? secretsHandlers.openSecretEditor(...args)
    : undefined;
}

function openProviderStatusModal(...args) {
  return typeof secretsHandlers.openProviderStatusModal === 'function'
    ? secretsHandlers.openProviderStatusModal(...args)
    : undefined;
}

function closeProviderStatusModal(...args) {
  return typeof secretsHandlers.closeProviderStatusModal === 'function'
    ? secretsHandlers.closeProviderStatusModal(...args)
    : undefined;
}

function isProviderStatusModalOpen(...args) {
  return typeof secretsHandlers.isProviderStatusModalOpen === 'function'
    ? !!secretsHandlers.isProviderStatusModalOpen(...args)
    : false;
}

function deleteOptionsSecret(...args) {
  return typeof secretsHandlers.deleteOptionsSecret === 'function'
    ? secretsHandlers.deleteOptionsSecret(...args)
    : undefined;
}

function handleSecretCommand(...args) {
  return typeof secretsHandlers.handleSecretCommand === 'function'
    ? secretsHandlers.handleSecretCommand(...args)
    : undefined;
}

export {
  closeProviderStatusModal,
  deleteOptionsSecret,
  handleSecretCommand,
  hasSecretsHandler,
  invalidateOptionsSecrets,
  isProviderStatusModalOpen,
  openProviderStatusModal,
  openSecretEditor,
  refreshOptionsSecrets,
  setSecretsHandlers,
};
