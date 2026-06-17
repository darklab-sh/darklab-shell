import {
  hasRuntimeHandler,
  logClientError
} from "./static-chunk-i34eiczq.4bb950c346dc.js";

// app/static/js/core/config.js
var CONFIG_GLOBAL = typeof window !== "undefined" ? window : globalThis;
function _configLogClientEvent(context, err, details) {
  if (typeof hasRuntimeHandler === "function" && hasRuntimeHandler("logClientError") && typeof logClientError === "function") {
    logClientError(context, err, details);
  } else if (typeof CONFIG_GLOBAL?.logClientError === "function") {
    CONFIG_GLOBAL.logClientError(context, err, details);
  }
}
function _configSourceDetails(config, source) {
  const lazyAssetUrls = config && typeof config.lazy_asset_urls === "object" && !Array.isArray(config.lazy_asset_urls) ? config.lazy_asset_urls : {};
  return {
    source,
    workspace_enabled: config?.workspace_enabled === true,
    lazy_asset_count: Object.keys(lazyAssetUrls).length
  };
}
function readBootstrappedAppConfig() {
  if (typeof document !== "undefined") {
    const node = document.getElementById("app-config-json");
    if (node && node.textContent) {
      try {
        const parsed = JSON.parse(node.textContent);
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed;
      } catch (err) {
        const fallback = CONFIG_GLOBAL?.APP_CONFIG && typeof CONFIG_GLOBAL.APP_CONFIG === "object" && !Array.isArray(CONFIG_GLOBAL.APP_CONFIG) ? "window.APP_CONFIG" : "empty";
        _configLogClientEvent("failed to parse app config bootstrap", err, {
          event: "APP_CONFIG_PARSE_FAILED",
          level: "warning",
          source: "app-config-json",
          fallback,
          text_length: String(node.textContent || "").length
        });
      }
    }
  }
  if (CONFIG_GLOBAL?.APP_CONFIG && typeof CONFIG_GLOBAL.APP_CONFIG === "object" && !Array.isArray(CONFIG_GLOBAL.APP_CONFIG)) {
    return CONFIG_GLOBAL.APP_CONFIG;
  }
  return {};
}
var APP_CONFIG = readBootstrappedAppConfig();
_configLogClientEvent("app config loaded", null, {
  event: "APP_CONFIG_LOADED",
  level: "info",
  ..._configSourceDetails(APP_CONFIG, CONFIG_GLOBAL?.APP_CONFIG && typeof CONFIG_GLOBAL.APP_CONFIG === "object" && !Array.isArray(CONFIG_GLOBAL.APP_CONFIG) ? "window.APP_CONFIG" : "app-config-json")
});
function getAppConfig() {
  return APP_CONFIG;
}
function setAppConfig(config) {
  APP_CONFIG = config && typeof config === "object" && !Array.isArray(config) ? config : {};
  if (typeof window !== "undefined") CONFIG_GLOBAL.APP_CONFIG = APP_CONFIG;
  return APP_CONFIG;
}
if (typeof window !== "undefined") {
  CONFIG_GLOBAL.APP_CONFIG = APP_CONFIG;
  CONFIG_GLOBAL.DarklabConfig = Object.freeze({
    getAppConfig,
    readBootstrappedAppConfig,
    setAppConfig
  });
}

export {
  APP_CONFIG,
  getAppConfig
};
