// ── Shared utility module ──
function readBootstrappedAppConfig() {
  if (typeof document !== 'undefined') {
    const node = document.getElementById('app-config-json');
    if (node && node.textContent) {
      try {
        const parsed = JSON.parse(node.textContent);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed;
      } catch (err) {
        if (typeof logClientError === 'function') logClientError('failed to parse app config bootstrap', err);
      }
    }
  }
  if (typeof window !== 'undefined'
    && window.APP_CONFIG
    && typeof window.APP_CONFIG === 'object'
    && !Array.isArray(window.APP_CONFIG)) {
    return window.APP_CONFIG;
  }
  return {};
}

let APP_CONFIG = readBootstrappedAppConfig();
if (typeof window !== 'undefined') window.APP_CONFIG = APP_CONFIG;
