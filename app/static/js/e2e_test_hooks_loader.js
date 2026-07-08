// Keep Playwright-only browser hooks out of ordinary shell startup.

const E2E_HOOK_LOADER_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function _shouldLoadE2ETestHooks() {
  return !!(
    E2E_HOOK_LOADER_GLOBAL
    && E2E_HOOK_LOADER_GLOBAL.navigator
    && E2E_HOOK_LOADER_GLOBAL.navigator.webdriver === true
  );
}

const e2eTestHooksReady = _shouldLoadE2ETestHooks()
  ? import('./e2e_test_hooks.js')
    .then(() => true)
    .catch((err) => {
      const consoleApi = E2E_HOOK_LOADER_GLOBAL && E2E_HOOK_LOADER_GLOBAL.console;
      if (consoleApi && typeof consoleApi.error === 'function') {
        consoleApi.error('[darklab] failed to load e2e test hooks', err);
      }
      return false;
    })
  : Promise.resolve(false);

if (E2E_HOOK_LOADER_GLOBAL && typeof Object.defineProperty === 'function') {
  Object.defineProperty(E2E_HOOK_LOADER_GLOBAL, '__darklabE2ETestHooksReady', {
    configurable: true,
    enumerable: false,
    value: e2eTestHooksReady,
  });
}

export { e2eTestHooksReady };
