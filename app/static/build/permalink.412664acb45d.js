// app/static/js/core/utils.js
function escapeHtml(t) {
  return t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function escapeRegex(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
function normalizeRedactionRules(rules) {
  if (!Array.isArray(rules)) return [];
  return rules.filter((rule) => rule && typeof rule === "object").map((rule) => {
    const pattern = typeof rule.pattern === "string" ? rule.pattern : "";
    if (!pattern.trim()) return null;
    const replacement = typeof rule.replacement === "string" ? rule.replacement : "[redacted]";
    const flags = typeof rule.flags === "string" ? Array.from(new Set(rule.flags.toLowerCase().split("").filter((ch) => ch === "i" || ch === "m"))).join("") : "";
    try {
      return {
        label: typeof rule.label === "string" ? rule.label.trim() : "",
        pattern,
        replacement,
        flags,
        regex: new RegExp(pattern, `g${flags}`)
      };
    } catch (_) {
      return null;
    }
  }).filter(Boolean);
}
function applyRedactionRules(text, rules) {
  let value = String(text ?? "");
  for (const rule of normalizeRedactionRules(rules)) {
    value = value.replace(rule.regex, rule.replacement);
  }
  return value;
}
function redactLineEntries(entries, rules) {
  return (Array.isArray(entries) ? entries : []).map((item) => {
    if (typeof item === "string") return applyRedactionRules(item, rules);
    if (!item || typeof item !== "object" || typeof item.text !== "string") return null;
    return {
      ...item,
      text: applyRedactionRules(item.text, rules)
    };
  }).filter(Boolean);
}
var RAW_ONLY_INTEL_PLACEHOLDER = "Intel data omitted from share";
function _isRawOnlyIntelEntry(item) {
  return !!(item && typeof item === "object" && String(item.command_root || "").trim().toLowerCase() === "intel");
}
function _rawOnlyPlaceholderEntry(source = {}) {
  const entry = {
    text: RAW_ONLY_INTEL_PLACEHOLDER,
    cls: "notice",
    raw_only: true,
    command_root: "intel"
  };
  if (typeof source.tsC === "string") entry.tsC = source.tsC;
  if (typeof source.tsE === "string") entry.tsE = source.tsE;
  if (Number.isInteger(source.line_number)) entry.line_number = source.line_number;
  return entry;
}
function omitRawOnlyLineEntries(entries) {
  const omitted = [];
  let inIntelGroup = false;
  for (const item of Array.isArray(entries) ? entries : []) {
    if (_isRawOnlyIntelEntry(item)) {
      if (!inIntelGroup) {
        omitted.push(_rawOnlyPlaceholderEntry(item));
        inIntelGroup = true;
      }
      continue;
    }
    inIntelGroup = false;
    if (typeof item === "string") omitted.push(item);
    else if (item && typeof item === "object") omitted.push({ ...item });
  }
  return omitted;
}
function renderMotd(text) {
  return escapeHtml(text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>').replace(/\n/g, "<br>");
}
function _copyTextFallback(text) {
  return new Promise((resolve, reject) => {
    if (typeof document === "undefined" || !document.body) {
      reject(new Error("Clipboard is not available"));
      return;
    }
    const textarea = document.createElement("textarea");
    textarea.value = String(text);
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.top = "-9999px";
    textarea.style.left = "-9999px";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);
    let copied = false;
    try {
      copied = typeof document.execCommand === "function" && document.execCommand("copy");
    } catch (_) {
      copied = false;
    }
    textarea.remove();
    if (copied) resolve(true);
    else reject(new Error("Copy command failed"));
  });
}
async function copyTextToClipboard2(text) {
  const value = String(text ?? "");
  if (!value) throw new Error("Cannot copy empty text");
  if (typeof navigator !== "undefined" && navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch (_) {
    }
  }
  return _copyTextFallback(value);
}
function downloadBlobAsAttachment2(blob, filename, options = {}) {
  const opts = options && typeof options === "object" ? options : {};
  const { revokeDelayMs = 2e3, container = null } = opts;
  if (typeof URL === "undefined" || typeof URL.createObjectURL !== "function") {
    throw new Error("Blob downloads are not available");
  }
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename || "download";
  const parent = container && typeof container.appendChild === "function" ? container : document.body;
  parent.appendChild(anchor);
  anchor.click();
  anchor.remove();
  if (typeof URL.revokeObjectURL !== "function") return;
  let revoked = false;
  const revoke = () => {
    if (revoked) return;
    revoked = true;
    URL.revokeObjectURL(url);
  };
  if (typeof window !== "undefined" && typeof window.setTimeout === "function") {
    window.setTimeout(revoke, revokeDelayMs);
  } else if (typeof setTimeout === "function") {
    setTimeout(revoke, revokeDelayMs);
  }
  if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
    window.addEventListener("pagehide", revoke, { once: true });
  }
}
function downloadUrlAsAttachment(url, options = {}) {
  const href = String(url || "").trim();
  if (!href) throw new Error("Download URL is required");
  const opts = options && typeof options === "object" ? options : {};
  const anchor = document.createElement("a");
  anchor.href = href;
  if (opts.filename) anchor.download = String(opts.filename);
  anchor.rel = "noopener";
  const parent = opts.container && typeof opts.container.appendChild === "function" ? opts.container : document.body;
  parent.appendChild(anchor);
  anchor.click();
  anchor.remove();
}
async function shareUrl(url) {
  const canShare = typeof navigator !== "undefined" && typeof navigator.share === "function";
  try {
    await copyTextToClipboard2(url);
  } catch (_) {
    if (typeof window !== "undefined" && typeof window.prompt === "function") {
      window.prompt("Copy the link:", url);
    }
    return;
  }
  if (canShare) {
    showToast2("Link copied to clipboard", "success", {
      label: "share ↗",
      onClick: () => {
        navigator.share({ url }).catch(() => {
        });
      }
    });
  } else {
    showToast2("Link copied to clipboard");
  }
}
function showToast2(msg, tone = "success", action = null) {
  const toast = document.getElementById("permalink-toast");
  const isError = tone === "error" || /^(failed|unable|error|\[.*error\])/i.test(String(msg || ""));
  toast.classList.remove("toast-has-action");
  toast.textContent = msg;
  if (action && action.label && typeof action.onClick === "function") {
    const btn = document.createElement("button");
    btn.className = "toast-action-btn";
    btn.textContent = action.label;
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      toast.classList.remove("show");
      toast.classList.remove("toast-has-action");
      action.onClick();
    }, { once: true });
    toast.classList.add("toast-has-action");
    toast.appendChild(btn);
  }
  toast.classList.toggle("toast-error", isError);
  toast.classList.toggle("toast-success", !isError);
  toast.classList.add("show");
  setTimeout(() => {
    toast.classList.remove("show");
    toast.classList.remove("toast-has-action");
  }, action ? 5e3 : 2500);
}
if (typeof window !== "undefined") {
  Object.assign(window, {
    escapeHtml,
    escapeRegex,
    normalizeRedactionRules,
    applyRedactionRules,
    redactLineEntries,
    omitRawOnlyLineEntries,
    renderMotd,
    copyTextToClipboard: copyTextToClipboard2,
    downloadUrlAsAttachment,
    shareUrl,
    showToast: showToast2
  });
  if (typeof window.downloadBlobAsAttachment !== "function") {
    window.downloadBlobAsAttachment = downloadBlobAsAttachment2;
  }
}

// app/static/js/core/run_output_model.js
var DarklabRunOutputModel = (function(global) {
  "use strict";
  const LINE_EVENT_SCHEMA_VERSION = 1;
  const LINE_KIND_VALUES = Object.freeze(["info", "notice", "warn", "error"]);
  const LINE_ROLE_VALUES = Object.freeze([
    "body",
    "prompt-echo",
    "section-header",
    "kv",
    "help-row",
    "pty-marker",
    "progress",
    "status-line",
    "success",
    "denied",
    "exit-ok",
    "exit-fail"
  ]);
  const LINE_SIGNAL_VALUES = Object.freeze(["findings", "warnings", "errors", "summaries"]);
  const LINE_NOISE_KIND_VALUES = Object.freeze(["progress", "status", "boilerplate"]);
  const LineKind = Object.freeze({
    INFO: "info",
    NOTICE: "notice",
    WARN: "warn",
    ERROR: "error"
  });
  const LineRole = Object.freeze({
    BODY: "body",
    PROMPT_ECHO: "prompt-echo",
    SECTION_HEADER: "section-header",
    KV: "kv",
    HELP_ROW: "help-row",
    PTY_MARKER: "pty-marker",
    PROGRESS: "progress",
    STATUS_LINE: "status-line",
    SUCCESS: "success",
    DENIED: "denied",
    EXIT_OK: "exit-ok",
    EXIT_FAIL: "exit-fail"
  });
  const LineSignal = Object.freeze({
    FINDINGS: "findings",
    WARNINGS: "warnings",
    ERRORS: "errors",
    SUMMARIES: "summaries"
  });
  const LineNoiseKind = Object.freeze({
    PROGRESS: "progress",
    STATUS: "status",
    BOILERPLATE: "boilerplate"
  });
  const LEGACY_KIND_BY_CLS = Object.freeze({
    "": LineKind.INFO,
    output: LineKind.INFO,
    out: LineKind.INFO,
    cmd: LineKind.INFO,
    notice: LineKind.NOTICE,
    "builtin-note": LineKind.NOTICE,
    "welcome-output": LineKind.NOTICE,
    warn: LineKind.WARN,
    warning: LineKind.WARN,
    error: LineKind.ERROR
  });
  const LEGACY_ROLE_BY_CLS = Object.freeze({
    "": LineRole.BODY,
    output: LineRole.BODY,
    out: LineRole.BODY,
    notice: LineRole.BODY,
    warn: LineRole.BODY,
    warning: LineRole.BODY,
    error: LineRole.BODY,
    "builtin-note": LineRole.BODY,
    "builtin-spacer": LineRole.BODY,
    "welcome-output": LineRole.BODY,
    cmd: LineRole.PROMPT_ECHO,
    "prompt-echo": LineRole.PROMPT_ECHO,
    "builtin-section": LineRole.SECTION_HEADER,
    "builtin-kv": LineRole.KV,
    "builtin-help-row": LineRole.HELP_ROW,
    "builtin-faq-q": LineRole.HELP_ROW,
    "builtin-faq-a": LineRole.HELP_ROW,
    "pty-marker": LineRole.PTY_MARKER,
    progress: LineRole.PROGRESS,
    "status-line": LineRole.STATUS_LINE,
    "builtin-success": LineRole.SUCCESS,
    denied: LineRole.DENIED,
    "exit-ok": LineRole.EXIT_OK,
    "exit-fail": LineRole.EXIT_FAIL
  });
  const KIND_LEGACY_CLS = Object.freeze({
    info: "",
    notice: "notice",
    warn: "warn",
    error: "error"
  });
  const ROLE_LEGACY_CLS = Object.freeze({
    body: "",
    "prompt-echo": "prompt-echo",
    "section-header": "builtin-section",
    kv: "builtin-kv",
    "help-row": "builtin-help-row",
    "pty-marker": "pty-marker",
    progress: "progress",
    "status-line": "status-line",
    success: "builtin-success",
    denied: "denied",
    "exit-ok": "exit-ok",
    "exit-fail": "exit-fail"
  });
  const NOISE_KIND_BY_ROLE = Object.freeze({
    progress: LineNoiseKind.PROGRESS,
    "status-line": LineNoiseKind.STATUS
  });
  function legacyClsTokens(value) {
    const text = String(value || "").trim();
    if (!text) return [""];
    return text.split(/\s+/).filter(Boolean);
  }
  function legacyClsToKind(value) {
    const tokens = legacyClsTokens(value);
    for (const token of tokens) {
      if (Object.prototype.hasOwnProperty.call(LEGACY_KIND_BY_CLS, token)) return LEGACY_KIND_BY_CLS[token];
    }
    return LineKind.INFO;
  }
  function legacyClsToRole(value) {
    const tokens = legacyClsTokens(value);
    for (const token of tokens) {
      if (Object.prototype.hasOwnProperty.call(LEGACY_ROLE_BY_CLS, token)) return LEGACY_ROLE_BY_CLS[token];
    }
    return LineRole.BODY;
  }
  function collectUnknown(unknownCollector, family, value) {
    if (typeof unknownCollector === "function") unknownCollector(family, String(value));
  }
  function enumValue(values, value, fallback, family, unknownCollector) {
    if (value === void 0 || value === null || value === "") return fallback;
    const stringValue = String(value);
    if (values.includes(stringValue)) return stringValue;
    collectUnknown(unknownCollector, family, stringValue);
    return fallback;
  }
  function optionalInt(value) {
    if (value === void 0 || value === null || typeof value === "boolean") return null;
    const parsed = Number.parseInt(String(value), 10);
    return Number.isFinite(parsed) ? parsed : null;
  }
  function entityFromWire(payload) {
    if (!payload || typeof payload !== "object") return null;
    const type = String(payload.type || "").trim();
    const canonicalValue = String(payload.canonical_value || "").trim();
    if (!type || !canonicalValue) return null;
    let start = optionalInt(payload.start);
    let end = optionalInt(payload.end);
    if (start === null || end === null) {
      start = null;
      end = null;
    }
    return {
      type,
      value: String(payload.value || "").trim() || canonicalValue,
      canonical_value: canonicalValue,
      confidence: String(payload.confidence || "").trim() || "medium",
      source_line: optionalInt(payload.source_line),
      start,
      end
    };
  }
  function entityToWire(entity) {
    const payload = {
      type: entity.type,
      value: entity.value,
      canonical_value: entity.canonical_value,
      confidence: entity.confidence
    };
    if (entity.source_line !== null && entity.source_line !== void 0) payload.source_line = entity.source_line;
    if (entity.start !== null && entity.start !== void 0) payload.start = entity.start;
    if (entity.end !== null && entity.end !== void 0) payload.end = entity.end;
    return payload;
  }
  function signalsFromWire(value, unknownCollector) {
    if (!Array.isArray(value)) return [];
    const signals = [];
    value.forEach((item) => {
      const signal = String(item);
      if (LINE_SIGNAL_VALUES.includes(signal)) {
        signals.push(signal);
      } else {
        collectUnknown(unknownCollector, "signal", signal);
      }
    });
    return signals;
  }
  function entitiesFromWire(value) {
    if (!Array.isArray(value)) return [];
    return value.map(entityFromWire).filter(Boolean);
  }
  function legacyClsForEvent(event) {
    if (event.legacy_cls) return String(event.legacy_cls);
    const role = event.role || LineRole.BODY;
    if (role !== LineRole.BODY) return ROLE_LEGACY_CLS[role] || "";
    return KIND_LEGACY_CLS[event.kind || LineKind.INFO] || "";
  }
  function noiseKindForRole(role) {
    return NOISE_KIND_BY_ROLE[role] || null;
  }
  function noiseKindForEvent(event) {
    if (!event || Array.isArray(event.signals) && event.signals.length) return null;
    if (event.kind === LineKind.WARN || event.kind === LineKind.ERROR) return null;
    if (event.noise_kind) return event.noise_kind;
    return noiseKindForRole(event.role || LineRole.BODY);
  }
  function isNoiseLineEvent(event) {
    return noiseKindForEvent(event) !== null;
  }
  function legacyPayload(event) {
    const payload = {
      text: String(event.text || ""),
      cls: legacyClsForEvent(event),
      tsC: String(event.ts_clock || event.tsC || ""),
      tsE: String(event.ts_elapsed || event.tsE || "")
    };
    if (Array.isArray(event.signals) && event.signals.length) payload.signals = event.signals.slice();
    if (event.line_index !== null && event.line_index !== void 0) payload.line_index = event.line_index;
    if (event.command_root) payload.command_root = String(event.command_root);
    if (event.target) payload.target = String(event.target);
    if (Array.isArray(event.entities) && event.entities.length) payload.entities = event.entities.map(entityToWire);
    const noiseKind = noiseKindForEvent(event);
    if (noiseKind) {
      payload.noise_kind = noiseKind;
      if (event.noise_reason) payload.noise_reason = String(event.noise_reason);
    }
    return payload;
  }
  function fromWireLineEvent(payload, unknownCollector) {
    const item = payload && typeof payload === "object" ? payload : {};
    const clsValue = item.cls || "";
    const kind = enumValue(LINE_KIND_VALUES, item.kind, legacyClsToKind(clsValue), "kind", unknownCollector);
    const role = enumValue(LINE_ROLE_VALUES, item.role, legacyClsToRole(clsValue), "role", unknownCollector);
    const noiseKind = enumValue(
      LINE_NOISE_KIND_VALUES,
      item.noise_kind,
      noiseKindForRole(role),
      "noise_kind",
      unknownCollector
    );
    return {
      text: String(item.text || ""),
      kind,
      role,
      legacy_cls: String(clsValue || ""),
      ts_clock: String(item.tsC || ""),
      ts_elapsed: String(item.tsE || ""),
      signals: signalsFromWire(item.signals, unknownCollector),
      line_index: optionalInt(item.line_index),
      command_root: String(item.command_root || ""),
      target: String(item.target || ""),
      entities: entitiesFromWire(item.entities),
      noise_kind: noiseKind,
      noise_reason: noiseKind ? String(item.noise_reason || "") : ""
    };
  }
  function toLegacyWireLineEvent(event) {
    return legacyPayload(event || {});
  }
  function toWireLineEvent(event) {
    const payload = legacyPayload(event || {});
    payload.v = LINE_EVENT_SCHEMA_VERSION;
    payload.kind = event && event.kind || LineKind.INFO;
    payload.role = event && event.role || LineRole.BODY;
    return payload;
  }
  function eventSearchText(event) {
    return String(event && event.text || "");
  }
  const api = Object.freeze({
    LINE_EVENT_SCHEMA_VERSION,
    LINE_KIND_VALUES,
    LINE_NOISE_KIND_VALUES,
    LINE_ROLE_VALUES,
    LINE_SIGNAL_VALUES,
    LineKind,
    LineNoiseKind,
    LineRole,
    LineSignal,
    eventSearchText,
    fromWireLineEvent,
    isNoiseLineEvent,
    legacyClsToKind,
    legacyClsToRole,
    noiseKindForEvent,
    noiseKindForRole,
    toLegacyWireLineEvent,
    toWireLineEvent
  });
  global.DarklabRunOutputModel = api;
  return api;
})(typeof window !== "undefined" ? window : globalThis);

// app/static/js/core/output_core.js
var DarklabOutputCore = (function(global) {
  const OUTPUT_SIGNAL_SCOPES = Object.freeze(["findings", "warnings", "errors", "summaries"]);
  const OUTPUT_SIGNAL_SUMMARY_CLASSES = Object.freeze([
    "builtin-signal-summary-header",
    "builtin-signal-summary-section",
    "builtin-signal-summary-row",
    "builtin-signal-summary-note",
    "builtin-signal-summary-sep"
  ]);
  const OUTPUT_COMMAND_OUTCOME_SUMMARY_CLASSES = Object.freeze([
    "command-outcome-summary",
    "command-outcome-summary-title",
    "command-outcome-summary-row",
    "command-outcome-summary-note"
  ]);
  const OUTPUT_SYNTHETIC_SUMMARY_CLASSES = Object.freeze([
    ...OUTPUT_SIGNAL_SUMMARY_CLASSES,
    ...OUTPUT_COMMAND_OUTCOME_SUMMARY_CLASSES
  ]);
  function promptIdentityPrefix(rawPrefix = "") {
    let prefix = String(rawPrefix || "").trim() || "anon@darklab";
    if (prefix.endsWith("$")) prefix = prefix.slice(0, -1).trimEnd();
    prefix = prefix.replace(/:[^\s:]+$/, "").trim() || "anon@darklab";
    return prefix;
  }
  function promptIdentityFromParts(username = "", domain = "") {
    const cleanUsername = String(username || "").trim() || "anon";
    const cleanDomain = String(domain || "").trim() || "darklab.sh";
    return `${cleanUsername}@${cleanDomain}`;
  }
  function normalizeWorkspaceCwd(rawPath = "") {
    return String(rawPath || "").split("/").map((part) => String(part || "").trim()).filter(Boolean).join("/");
  }
  function workspaceDisplayPath(path = "") {
    const normalized = normalizeWorkspaceCwd(path);
    return normalized ? `/${normalized}` : "/";
  }
  function buildPromptLabel(rawPrefix = "", path = "~") {
    return `${promptIdentityPrefix(rawPrefix)}:${String(path || "~")} $`;
  }
  function buildPromptLabelFromParts(username = "", domain = "", path = "~") {
    return `${promptIdentityFromParts(username, domain)}:${String(path || "~")} $`;
  }
  function _escapeRegex(text) {
    return String(text || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }
  function stripPromptLabelFromEchoText(text = "", currentLabel = "", identityPrefix = "") {
    const value = String(text || "");
    const current = String(currentLabel || "");
    if (current && value.startsWith(current)) return value.slice(current.length).replace(/^\s+/, "");
    const identity = promptIdentityPrefix(identityPrefix);
    const legacyPattern = new RegExp(`^${_escapeRegex(identity)}:[^\\s]+\\$\\s*`);
    if (legacyPattern.test(value)) return value.replace(legacyPattern, "");
    const promptShapedPattern = /^[^\s:]+@[^\s:]+:[^\s]+\$\s*/;
    if (promptShapedPattern.test(value)) return value.replace(promptShapedPattern, "");
    if (value === "$") return "";
    if (value.startsWith("$ ")) return value.slice(2);
    return value;
  }
  function formatOutputPrefix(index, tsText, includeTimestamp, lineMode, timestampMode) {
    const parts = [];
    if (lineMode === "on") parts.push(String(index));
    if (includeTimestamp && tsText && (timestampMode === "elapsed" || timestampMode === "clock")) {
      parts.push(tsText);
    }
    return parts.join(" ");
  }
  function emptySignalCounts() {
    return { findings: 0, warnings: 0, errors: 0, summaries: 0 };
  }
  function isSignalSummaryClassName(cls) {
    return OUTPUT_SIGNAL_SUMMARY_CLASSES.includes(cls);
  }
  function isSyntheticSummaryClassName(cls) {
    return OUTPUT_SYNTHETIC_SUMMARY_CLASSES.includes(cls);
  }
  function _normalizeOutcomeItem(item) {
    if (item == null) return null;
    if (typeof item === "string" || typeof item === "number" || typeof item === "boolean") {
      const value2 = String(item).trim();
      return value2 ? { value: value2 } : null;
    }
    if (typeof item !== "object") return null;
    const label = String(item.label || item.key || "").trim();
    const value = String(item.value || item.text || item.summary || "").trim();
    const tone = String(item.tone || "").trim();
    if (!label && !value) return null;
    return {
      ...label ? { label } : {},
      value,
      ...tone ? { tone } : {}
    };
  }
  function normalizeCommandOutcomeSummary(raw) {
    if (!raw) return null;
    if (typeof raw === "string" || typeof raw === "number" || typeof raw === "boolean") {
      const value = String(raw).trim();
      if (!value) return null;
      return {
        kind: "command_outcome",
        title: "Command outcome",
        items: [{ value }]
      };
    }
    if (typeof raw !== "object") return null;
    const title = String(raw.title || raw.heading || "Command outcome").trim() || "Command outcome";
    const sourceItems = Array.isArray(raw.items) ? raw.items : Array.isArray(raw.lines) ? raw.lines : Array.isArray(raw.summary) ? raw.summary : [];
    const items = sourceItems.map(_normalizeOutcomeItem).filter(Boolean);
    if (!items.length && typeof raw.text === "string" && raw.text.trim()) {
      items.push({ value: raw.text.trim() });
    }
    if (!items.length) return null;
    return {
      kind: "command_outcome",
      title,
      items
    };
  }
  function _plainOutcomeLineText(line) {
    return String(line && typeof line === "object" ? line.text || "" : line || "").replace(/\x1b\[[0-9;?]*[ -/]*[@-~]/g, "").trimEnd();
  }
  function _outcomeCommandRoot(command = "") {
    return String(command || "").trim().split(/\s+/, 1)[0].toLowerCase();
  }
  function _outcomeLines(lines) {
    const model = window.DarklabRunOutputModel || null;
    return (Array.isArray(lines) ? lines : []).filter((line) => line && typeof line === "object").filter((line) => {
      const role = String(line.role || "").trim();
      const cls = String(line.cls || "").split(/\s+/).filter(Boolean);
      if (role === "prompt-echo" || role === "exit-ok" || role === "exit-fail") return false;
      if (cls.includes("prompt-echo") || cls.includes("exit-ok") || cls.includes("exit-fail")) return false;
      if (model && typeof model.isNoiseLineEvent === "function") {
        try {
          if (model.isNoiseLineEvent(model.fromWireLineEvent(line))) return false;
        } catch (_) {
        }
      }
      return !cls.some((name) => isSyntheticSummaryClassName(name));
    }).map(_plainOutcomeLineText).filter(Boolean);
  }
  function _formatLimitedList(values, limit = 8) {
    const unique = Array.from(new Set(values.map((value) => String(value || "").trim()).filter(Boolean)));
    if (unique.length <= limit) return unique.join(", ");
    return `${unique.slice(0, limit).join(", ")} and ${unique.length - limit} more`;
  }
  function _pushOutcomeItem(items, label, value) {
    const text = String(value || "").trim();
    if (text) items.push({ label, value: text });
  }
  function _parseNmapOutcome(lines) {
    const openPorts = [];
    const osHints = [];
    let hostsUp = "";
    lines.forEach((line) => {
      const portMatch = line.match(/^\s*(\d{1,5}\/(?:tcp|udp))\s+open\S*\s+([^\s]+)?\s*(.*)$/i);
      if (portMatch) {
        const port = portMatch[1].toLowerCase();
        const service = String(portMatch[2] || "").trim();
        const version = String(portMatch[3] || "").replace(/\s+/g, " ").trim();
        openPorts.push([port, service, version].filter(Boolean).join(" "));
        return;
      }
      const doneMatch = line.match(/Nmap done:\s+.*\((\d+)\s+hosts?\s+up\)/i);
      if (doneMatch) hostsUp = `${Number(doneMatch[1]).toLocaleString()} up`;
      const serviceInfo = line.match(/Service Info:\s*(.+)$/i);
      if (serviceInfo) osHints.push(serviceInfo[1].replace(/\s+/g, " ").trim());
      const osDetails = line.match(/(?:OS details|Running):\s*(.+)$/i);
      if (osDetails) osHints.push(osDetails[1].replace(/\s+/g, " ").trim());
    });
    const items = [];
    _pushOutcomeItem(items, "Hosts", hostsUp);
    _pushOutcomeItem(items, "Open ports", openPorts.length ? `${openPorts.length.toLocaleString()} (${_formatLimitedList(openPorts, 10)})` : "");
    _pushOutcomeItem(items, "OS / service hints", _formatLimitedList(osHints, 3));
    return items.length ? { title: "Command outcome", items } : null;
  }
  function _parseDigOutcome(lines) {
    const recordTypes = [];
    const answerRecords = [];
    let status = "";
    let answerCount = null;
    let server = "";
    let queryTime = "";
    let inAnswer = false;
    lines.forEach((line) => {
      const statusMatch = line.match(/HEADER<<-[^,]*,\s*status:\s*([A-Z0-9_-]+)/i);
      if (statusMatch) status = statusMatch[1].toUpperCase();
      const answerMatch = line.match(/\bANSWER:\s*(\d+)/i);
      if (answerMatch) answerCount = Number(answerMatch[1]);
      if (/^;;\s*ANSWER SECTION:/i.test(line)) {
        inAnswer = true;
        return;
      }
      if (/^;;\s*(AUTHORITY|ADDITIONAL|QUESTION) SECTION:/i.test(line)) inAnswer = false;
      if (inAnswer && !line.startsWith(";")) {
        const parts = line.trim().split(/\s+/);
        const inIndex = parts.findIndex((part) => part.toUpperCase() === "IN");
        if (inIndex >= 0 && parts[inIndex + 1]) {
          const owner = String(parts[0] || "").replace(/\.$/, "");
          const recordType = parts[inIndex + 1].toUpperCase();
          const value = parts.slice(inIndex + 2).join(" ").trim();
          recordTypes.push(recordType);
          if (owner && recordType && value) answerRecords.push(`${owner} ${recordType} ${value}`);
        }
      }
      const serverMatch = line.match(/^;;\s*SERVER:\s*(.+)$/i);
      if (serverMatch) server = serverMatch[1].trim();
      const timeMatch = line.match(/^;;\s*Query time:\s*(.+)$/i);
      if (timeMatch) queryTime = timeMatch[1].trim();
    });
    const items = [];
    _pushOutcomeItem(items, "Status", status);
    _pushOutcomeItem(items, "Answers", answerCount == null ? "" : String(answerCount));
    _pushOutcomeItem(items, "Answer records", _formatLimitedList(answerRecords, 4));
    _pushOutcomeItem(items, "Record types", _formatLimitedList(recordTypes, 6));
    _pushOutcomeItem(items, "Resolver", server);
    _pushOutcomeItem(items, "Query time", queryTime);
    return items.length ? { title: "Command outcome", items } : null;
  }
  function _cleanNslookupName(value) {
    return String(value || "").trim().replace(/\.$/, "");
  }
  function _parseNslookupOutcome(lines) {
    const aRecords = [];
    const mxRecords = [];
    const txtRecords = [];
    const recordTypes = [];
    let resolver = "";
    let currentName = "";
    let inAnswer = false;
    lines.forEach((line) => {
      const serverMatch = line.match(/^Server:\s*(.+)$/i);
      if (serverMatch) {
        resolver = serverMatch[1].trim();
        return;
      }
      const resolverAddressMatch = line.match(/^Address:\s*(.+)$/i);
      if (!inAnswer && resolverAddressMatch) {
        const address = resolverAddressMatch[1].trim();
        resolver = resolver ? `${resolver} (${address})` : address;
        return;
      }
      if (/^Non-authoritative answer:/i.test(line)) {
        inAnswer = true;
        return;
      }
      if (/^Authoritative answers can be found from:/i.test(line)) {
        inAnswer = false;
        return;
      }
      const nameMatch = line.match(/^Name:\s*(.+)$/i);
      if (nameMatch) {
        currentName = _cleanNslookupName(nameMatch[1]);
        return;
      }
      const addressMatch = line.match(/^Address:\s*(.+)$/i);
      if (inAnswer && currentName && addressMatch) {
        recordTypes.push("A");
        aRecords.push(`${currentName} A ${addressMatch[1].trim()}`);
        return;
      }
      const mxMatch = line.match(/^(\S+)\s+mail exchanger\s*=\s*(.+)$/i);
      if (mxMatch) {
        recordTypes.push("MX");
        mxRecords.push(`${_cleanNslookupName(mxMatch[1])} MX ${mxMatch[2].trim().replace(/\.$/, "")}`);
        return;
      }
      const txtMatch = line.match(/^(\S+)\s+text\s*=\s*(.+)$/i);
      if (txtMatch) {
        recordTypes.push("TXT");
        txtRecords.push(`${_cleanNslookupName(txtMatch[1])} TXT ${txtMatch[2].trim().replace(/^"|"$/g, "")}`);
      }
    });
    const answerCount = aRecords.length + mxRecords.length + txtRecords.length;
    const items = [];
    _pushOutcomeItem(items, "Answers", answerCount ? String(answerCount) : "");
    _pushOutcomeItem(items, "A records", _formatLimitedList(aRecords, 4));
    _pushOutcomeItem(items, "MX records", _formatLimitedList(mxRecords, 4));
    _pushOutcomeItem(items, "TXT records", _formatLimitedList(txtRecords, 3));
    _pushOutcomeItem(items, "Record types", _formatLimitedList(recordTypes, 6));
    _pushOutcomeItem(items, "Resolver", resolver);
    return items.length ? { title: "Command outcome", items } : null;
  }
  function _parseCurlOutcome(lines) {
    const statuses = [];
    let contentType = "";
    let contentLength = "";
    let finalUrl = "";
    let tlsHint = "";
    lines.forEach((line) => {
      const statusMatch = line.match(/^\s*<*\s*HTTP\/(?:\d(?:\.\d)?|2|3)\s+(\d{3})(?:\s+(.+))?$/i);
      if (statusMatch) statuses.push(`${statusMatch[1]}${statusMatch[2] ? ` ${statusMatch[2].trim()}` : ""}`);
      const typeMatch = line.match(/^\s*<*\s*content-type:\s*(.+)$/i);
      if (typeMatch) contentType = typeMatch[1].trim();
      const lengthMatch = line.match(/^\s*<*\s*content-length:\s*(.+)$/i);
      if (lengthMatch) contentLength = lengthMatch[1].trim();
      const locationMatch = line.match(/^\s*<*\s*location:\s*(.+)$/i);
      if (locationMatch) finalUrl = locationMatch[1].trim();
      if (/SSL certificate problem|certificate verify failed|TLS.*alert|Failed to connect|Could not resolve host/i.test(line)) {
        tlsHint = line.replace(/^\s*curl:\s*/i, "").replace(/\s+/g, " ").trim();
      }
    });
    const items = [];
    _pushOutcomeItem(items, "Final status", statuses.length ? statuses[statuses.length - 1] : "");
    _pushOutcomeItem(items, "Redirects", statuses.length > 1 ? String(statuses.length - 1) : "");
    _pushOutcomeItem(items, "Final URL", finalUrl);
    _pushOutcomeItem(items, "Content type", contentType);
    _pushOutcomeItem(items, "Content length", contentLength);
    _pushOutcomeItem(items, "Connection / TLS", tlsHint);
    return items.length ? { title: "Command outcome", items } : null;
  }
  function _parseOpenSslOutcome(command, lines) {
    if (!/\bs_client\b/i.test(command)) return null;
    let subject = "";
    let issuer = "";
    let notBefore = "";
    let notAfter = "";
    let verify = "";
    let protocol = "";
    let cipher = "";
    lines.forEach((line) => {
      const subjectMatch = line.match(/^subject=\s*(.+)$/i);
      if (subjectMatch) subject = subjectMatch[1].trim();
      const issuerMatch = line.match(/^issuer=\s*(.+)$/i);
      if (issuerMatch) issuer = issuerMatch[1].trim();
      const beforeMatch = line.match(/^(?:notBefore|Not Before)\s*=\s*(.+)$/i);
      if (beforeMatch) notBefore = beforeMatch[1].trim();
      const afterMatch = line.match(/^(?:notAfter|Not After)\s*=\s*(.+)$/i);
      if (afterMatch) notAfter = afterMatch[1].trim();
      const verifyMatch = line.match(/Verify return code:\s*(.+)$/i);
      if (verifyMatch) verify = verifyMatch[1].trim();
      const protocolMatch = line.match(/^\s*Protocol\s*:\s*(.+)$/i);
      if (protocolMatch) protocol = protocolMatch[1].trim();
      const cipherMatch = line.match(/^\s*Cipher\s*:\s*(.+)$/i) || line.match(/^\s*New,\s*([^,]+),\s*Cipher is\s+(.+)$/i);
      if (cipherMatch) {
        if (!protocol && cipherMatch.length > 2) protocol = cipherMatch[1].trim();
        cipher = (cipherMatch.length > 2 ? cipherMatch[2] : cipherMatch[1]).trim();
      }
    });
    const items = [];
    _pushOutcomeItem(items, "Subject", subject);
    _pushOutcomeItem(items, "Issuer", issuer);
    _pushOutcomeItem(items, "Validity", [notBefore, notAfter].filter(Boolean).join(" to "));
    _pushOutcomeItem(items, "Verification", verify);
    _pushOutcomeItem(items, "Protocol", protocol);
    _pushOutcomeItem(items, "Cipher", cipher);
    return items.length ? { title: "Command outcome", items } : null;
  }
  function buildCommandOutcomeSummary(command = "", rawLines = []) {
    const root = _outcomeCommandRoot(command);
    const lines = _outcomeLines(rawLines);
    if (!root || !lines.length) return null;
    try {
      if (root === "nmap") return normalizeCommandOutcomeSummary(_parseNmapOutcome(lines));
      if (root === "dig") return normalizeCommandOutcomeSummary(_parseDigOutcome(lines));
      if (root === "nslookup") return normalizeCommandOutcomeSummary(_parseNslookupOutcome(lines));
      if (root === "curl") return normalizeCommandOutcomeSummary(_parseCurlOutcome(lines));
      if (root === "openssl") return normalizeCommandOutcomeSummary(_parseOpenSslOutcome(command, lines));
    } catch (_) {
      return null;
    }
    return null;
  }
  function lineHasClass(rawLine, className) {
    const cls = String(rawLine?.cls || "");
    return cls.split(/\s+/).filter(Boolean).includes(className);
  }
  function lineRole(rawLine) {
    const model = window.DarklabRunOutputModel || null;
    if (model && typeof model.fromWireLineEvent === "function") {
      return String(model.fromWireLineEvent(rawLine || {}).role || "body");
    }
    return lineHasClass(rawLine, "prompt-echo") ? "prompt-echo" : "body";
  }
  function isSignalCountableLine(rawLine) {
    if (!rawLine || lineRole(rawLine) === "prompt-echo") return false;
    const classes = String(rawLine.cls || "").split(/\s+/).filter(Boolean);
    return !classes.some((cls) => isSyntheticSummaryClassName(cls));
  }
  function isBuiltinCommandRoot(root, builtinRoots = []) {
    return !!root && Array.isArray(builtinRoots) && builtinRoots.includes(root);
  }
  function normalizeSignals(signals) {
    return Array.isArray(signals) ? signals.map((signal) => String(signal || "")).filter(Boolean) : [];
  }
  function normalizeEntities(entities) {
    if (!Array.isArray(entities)) return [];
    return entities.map((entity) => {
      if (!entity || typeof entity !== "object") return null;
      const type = String(entity.type || "").trim();
      const canonicalValue = String(entity.canonical_value || "").trim();
      if (!type || !canonicalValue) return null;
      const normalized = {
        type,
        value: String(entity.value || canonicalValue).trim() || canonicalValue,
        canonical_value: canonicalValue,
        confidence: String(entity.confidence || "medium").trim() || "medium"
      };
      if (Number.isInteger(entity.source_line)) normalized.source_line = entity.source_line;
      if (Number.isInteger(entity.start) && Number.isInteger(entity.end)) {
        normalized.start = entity.start;
        normalized.end = entity.end;
      }
      return normalized;
    }).filter(Boolean);
  }
  function countableSignalScopes(rawLine, builtinRoots = []) {
    if (!isSignalCountableLine(rawLine)) return [];
    const commandRoot = String(rawLine?.command_root || "").trim();
    if (isBuiltinCommandRoot(commandRoot, builtinRoots)) return [];
    const signals = normalizeSignals(rawLine?.signals);
    if (!signals.length) return [];
    const uniqueScopes = new Set(signals.filter((scope) => OUTPUT_SIGNAL_SCOPES.includes(scope)));
    return Array.from(uniqueScopes);
  }
  const api = Object.freeze({
    OUTPUT_COMMAND_OUTCOME_SUMMARY_CLASSES,
    OUTPUT_SIGNAL_SCOPES,
    buildCommandOutcomeSummary,
    buildPromptLabel,
    buildPromptLabelFromParts,
    countableSignalScopes,
    emptySignalCounts,
    formatOutputPrefix,
    isBuiltinCommandRoot,
    isSignalCountableLine,
    isSignalSummaryClassName,
    isSyntheticSummaryClassName,
    lineHasClass,
    normalizeCommandOutcomeSummary,
    normalizeEntities,
    normalizeSignals,
    normalizeWorkspaceCwd,
    promptIdentityFromParts,
    promptIdentityPrefix,
    stripPromptLabelFromEchoText,
    workspaceDisplayPath
  });
  global.DarklabOutputCore = api;
  return api;
})(typeof window !== "undefined" ? window : globalThis);

// app/static/js/export_html.js
(function() {
  const EXPORT_FONT_FILES = [
    { family: "JetBrains Mono", weight: 300, filename: "JetBrainsMono-300.ttf" },
    { family: "JetBrains Mono", weight: 400, filename: "JetBrainsMono-400.ttf" },
    { family: "JetBrains Mono", weight: 700, filename: "JetBrainsMono-700.ttf" },
    { family: "Syne", weight: 700, filename: "Syne-700.ttf" },
    { family: "Syne", weight: 800, filename: "Syne-800.ttf" }
  ];
  const EXPORT_THEME_VAR_NAMES = [
    "--bg",
    "--surface",
    "--border",
    "--border-bright",
    "--text",
    "--muted",
    "--green",
    "--green-dim",
    "--green-glow",
    "--amber",
    "--red",
    "--blue",
    "--theme-panel-bg",
    "--theme-panel-border",
    "--theme-panel-shadow",
    "--theme-terminal-bar-bg",
    "--terminal-font-size",
    "--terminal-line-height"
  ];
  function runOutputModel() {
    return window.DarklabRunOutputModel || null;
  }
  function fallbackLineEvent(line) {
    const cls = String(line && line.cls || "");
    return {
      text: String(line && line.text || ""),
      cls,
      kind: String(line && line.kind || (cls === "notice" ? "notice" : "info")),
      role: String(line && line.role || (["prompt-echo", "denied", "exit-ok", "exit-fail"].includes(cls) ? cls : "body")),
      tsC: String(line && line.tsC || ""),
      tsE: String(line && line.tsE || ""),
      signals: Array.isArray(line && line.signals) ? line.signals.map((signal) => String(signal || "")).filter(Boolean) : [],
      entities: Array.isArray(line && line.entities) ? line.entities : [],
      line_number: Number.isInteger(line && line.line_number) ? line.line_number : void 0
    };
  }
  function lineEventFromWire(line) {
    const model = runOutputModel();
    if (model && typeof model.fromWireLineEvent === "function") {
      const event = model.fromWireLineEvent(line || {});
      event.cls = lineLegacyClass(event);
      event.tsC = event.ts_clock || "";
      event.tsE = event.ts_elapsed || "";
      event.signals = Array.isArray(event.signals) ? event.signals : [];
      event.entities = Array.isArray(event.entities) ? event.entities : [];
      if (Number.isInteger(line && line.line_number)) event.line_number = line.line_number;
      return event;
    }
    return fallbackLineEvent(line || {});
  }
  function lineLegacyClass(event) {
    const model = runOutputModel();
    if (model && typeof model.toLegacyWireLineEvent === "function") {
      return String(model.toLegacyWireLineEvent(event || {}).cls || "");
    }
    return String(event && (event.legacy_cls || event.cls || (event.role !== "body" ? event.role : event.kind !== "info" ? event.kind : "")) || "");
  }
  function isPromptEchoEvent(event) {
    return String(event && event.role || "") === "prompt-echo";
  }
  function isPlainEvent(event) {
    const role = String(event && event.role || "body");
    const kind = String(event && event.kind || "info");
    return ["exit-ok", "exit-fail", "denied"].includes(role) || kind === "notice";
  }
  function escapeExportHtml(text) {
    return String(text ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function escapeExportAttr(text) {
    return escapeExportHtml(text).replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function renderExportPromptEcho(text) {
    const raw = String(text || "");
    const firstSpace = raw.indexOf(" ");
    const prefix = firstSpace === -1 ? raw : raw.slice(0, firstSpace);
    const remainder = firstSpace === -1 ? "" : raw.slice(firstSpace + 1);
    return '<span class="prompt-prefix">' + escapeExportHtml(prefix) + "</span>" + (remainder ? escapeExportHtml(" " + remainder) : "");
  }
  function exportEntityRanges(text, entities) {
    const length = String(text || "").length;
    return (Array.isArray(entities) ? entities : []).map((entity) => {
      const start = Number(entity && entity.start);
      const end = Number(entity && entity.end);
      if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end <= start || end > length) {
        return null;
      }
      return { start, end, entity };
    }).filter(Boolean).sort((a, b) => a.start - b.start || a.end - b.end).reduce((ranges, range) => {
      const previous = ranges[ranges.length - 1];
      if (previous && range.start < previous.end) return ranges;
      ranges.push(range);
      return ranges;
    }, []);
  }
  function renderExportEntityContent(text, entities, ansiToHtml) {
    const raw = String(text || "");
    const ranges = exportEntityRanges(raw, entities);
    if (!ranges.length) return ansiToHtml(raw);
    let cursor = 0;
    let html = "";
    ranges.forEach((range) => {
      if (range.start > cursor) html += ansiToHtml(raw.slice(cursor, range.start));
      const entity = range.entity || {};
      const entityType = String(entity.type || "");
      const entityValue = String(entity.canonical_value || entity.value || raw.slice(range.start, range.end));
      const tokenText = raw.slice(range.start, range.end);
      html += '<span class="export-entity-token" data-entity-type="' + escapeExportAttr(entityType) + '" data-entity-value="' + escapeExportAttr(entityValue) + '" title="Entity: ' + escapeExportAttr(entityValue) + '">' + ansiToHtml(tokenText) + "</span>";
      cursor = range.end;
    });
    if (cursor < raw.length) html += ansiToHtml(raw.slice(cursor));
    return html;
  }
  function exportLineBadgeHtml(line) {
    const kind = String(line && line.kind || "info");
    const signals = Array.isArray(line && line.signals) ? line.signals.map(String) : [];
    if (kind === "error") return '<span class="line-severity-badge line-severity-error">error</span>';
    if (kind === "warn") return '<span class="line-severity-badge line-severity-warn">warn</span>';
    if (signals.includes("findings")) return '<span class="line-severity-badge line-severity-finding">finding</span>';
    return "";
  }
  function buildExportLineSummary(rawLines) {
    const summary = {
      findings: 0,
      warnings: 0,
      errors: 0,
      entityTypes: {}
    };
    rawLines.forEach((rawLine) => {
      const line = lineEventFromWire(rawLine);
      const signals = Array.isArray(line.signals) ? line.signals.map(String) : [];
      if (signals.includes("findings")) summary.findings += 1;
      if (line.kind === "warn") summary.warnings += 1;
      if (line.kind === "error") summary.errors += 1;
      (Array.isArray(line.entities) ? line.entities : []).forEach((entity) => {
        const type = String(entity && entity.type || "").trim();
        if (type) summary.entityTypes[type] = (summary.entityTypes[type] || 0) + 1;
      });
    });
    return summary;
  }
  function buildExportSummaryHtml(summary) {
    const chips = [];
    if (summary.findings) chips.push(`findings ${summary.findings}`);
    if (summary.errors) chips.push(`errors ${summary.errors}`);
    if (summary.warnings) chips.push(`warnings ${summary.warnings}`);
    Object.entries(summary.entityTypes || {}).sort((a, b) => a[0].localeCompare(b[0])).slice(0, 8).forEach(([type, count]) => chips.push(`${type} ${count}`));
    if (!chips.length) return "";
    return '<section class="export-findings-summary">' + chips.map((chip) => `<span>${escapeExportHtml(chip)}</span>`).join("") + "</section>";
  }
  function renderExportLineContent(line, ansiToHtml) {
    const lineEvent = lineEventFromWire(line);
    const text = String(lineEvent.text || "");
    let content;
    if (isPromptEchoEvent(lineEvent)) {
      content = renderExportPromptEcho(text);
    } else if (isPlainEvent(lineEvent)) {
      content = escapeExportHtml(text);
    } else {
      content = renderExportEntityContent(text, lineEvent.entities, ansiToHtml);
    }
    return exportLineBadgeHtml(lineEvent) + content;
  }
  function exportTimestamp() {
    return (/* @__PURE__ */ new Date()).toISOString().replace(/[:.]/g, "-").slice(0, 19);
  }
  function buildExportMetaLine({ label = "", createdText = "" }) {
    const trimmedLabel = String(label || "").trim();
    const trimmedCreated = String(createdText || "").trim();
    if (trimmedLabel && trimmedCreated) return `${trimmedLabel} · ${trimmedCreated}`;
    return trimmedLabel || trimmedCreated;
  }
  function normalizeExportTranscriptLine(line) {
    if (typeof line === "string") {
      return lineEventFromWire({ text: line });
    }
    if (line && typeof line.text === "string") {
      return lineEventFromWire(line);
    }
    return null;
  }
  function normalizeExportTranscriptLines(lines, { stripTruncationNotices = false } = {}) {
    return (Array.isArray(lines) ? lines : []).map(normalizeExportTranscriptLine).filter((line) => {
      if (!line) return false;
      if (!stripTruncationNotices) return true;
      return !/^\[(?:preview|tab output) truncated/i.test(String(line.text || ""));
    });
  }
  function isCommandOutcomeSummaryLine(line) {
    const cls = String(line && line.cls || line && line.legacy_cls || "");
    return cls.split(/\s+/).includes("command-outcome-summary") || Boolean(line && line.command_outcome_summary === true);
  }
  function commandOutcomeItemText(item) {
    if (!item || typeof item !== "object") return "";
    const label = String(item.label || "").trim();
    const value = String(item.value || "").trim();
    if (label && value) return `${label}: ${value}`;
    return value || label;
  }
  function buildExportCommandOutcomeSummary(command, rawLines) {
    const core = window.DarklabOutputCore || null;
    if (!core || typeof core.buildCommandOutcomeSummary !== "function") return null;
    const normalizer = typeof core.normalizeCommandOutcomeSummary === "function" ? core.normalizeCommandOutcomeSummary : (value) => value;
    return normalizer(core.buildCommandOutcomeSummary(command, rawLines));
  }
  function commandOutcomeSummaryToLines(summary) {
    if (!summary || !Array.isArray(summary.items) || !summary.items.length) return [];
    const lines = [];
    const title = String(summary.title || "Command outcome").trim() || "Command outcome";
    lines.push({
      text: title,
      cls: "command-outcome-summary command-outcome-summary-title",
      command_outcome_summary: true
    });
    summary.items.forEach((item) => {
      const text = commandOutcomeItemText(item);
      if (!text) return;
      lines.push({
        text,
        cls: "command-outcome-summary command-outcome-summary-row",
        command_outcome_summary: true
      });
    });
    return lines;
  }
  function appendCommandOutcomeSummaryLines(rawLines, { command = "", enabled = true } = {}) {
    const normalized = normalizeExportTranscriptLines(rawLines);
    if (!enabled || normalized.some(isCommandOutcomeSummaryLine)) return normalized;
    const summary = buildExportCommandOutcomeSummary(command, normalized);
    if (!summary) return normalized;
    return normalized.concat(commandOutcomeSummaryToLines(summary));
  }
  function normalizeExportRunMeta(runMeta) {
    if (!runMeta) return null;
    return {
      exitCode: runMeta.exitCode !== void 0 ? runMeta.exitCode : runMeta.exit_code,
      duration: runMeta.duration || null,
      lines: runMeta.lines || null,
      version: runMeta.version || null
    };
  }
  function buildExportDocumentModel({
    appName = "",
    title = "",
    label = "",
    createdText = "",
    runMeta = null,
    rawLines = [],
    command = "",
    includeCommandOutcomeSummary = false
  }) {
    return {
      appName: String(appName || ""),
      title: String(title || ""),
      metaLine: buildExportMetaLine({ label, createdText }),
      runMeta: normalizeExportRunMeta(runMeta),
      rawLines: includeCommandOutcomeSummary ? appendCommandOutcomeSummaryLines(rawLines, { command, enabled: true }) : normalizeExportTranscriptLines(rawLines)
    };
  }
  function getThemeExportVars() {
    const registryCurrent = window.ThemeRegistry && window.ThemeRegistry.current && window.ThemeRegistry.current.vars && typeof window.ThemeRegistry.current.vars === "object" ? window.ThemeRegistry.current.vars : null;
    if (registryCurrent && Object.keys(registryCurrent).length) return registryCurrent;
    const current = window.ThemeCssVars && window.ThemeCssVars.current;
    if (current && typeof current === "object" && Object.keys(current).length) return current;
    const source = window.ThemeCssVars && window.ThemeCssVars.fallback;
    if (source && typeof source === "object") return source;
    const target = document.documentElement;
    const computed = getComputedStyle(target);
    const fallback = {};
    for (const name of EXPORT_THEME_VAR_NAMES) {
      const value = computed.getPropertyValue(name).trim();
      if (value) fallback[name] = value;
    }
    if (Object.keys(fallback).length) return fallback;
    return {};
  }
  function getThemeExportColorScheme() {
    const registryCurrent = window.ThemeRegistry && window.ThemeRegistry.current;
    if (registryCurrent && typeof registryCurrent.color_scheme === "string" && registryCurrent.color_scheme.trim()) {
      return registryCurrent.color_scheme.trim();
    }
    const colorSchemeMeta = document.querySelector('meta[name="color-scheme"]');
    if (colorSchemeMeta && typeof colorSchemeMeta.content === "string" && colorSchemeMeta.content.trim()) {
      return colorSchemeMeta.content.trim();
    }
    const docScheme = document.documentElement && document.documentElement.style ? document.documentElement.style.colorScheme : "";
    if (typeof docScheme === "string" && docScheme.trim()) return docScheme.trim();
    return "light dark";
  }
  function buildExportLinesHtml(rawLines, { getPrefix = () => "", ansiToHtml }) {
    const prefixes = rawLines.map((line, i) => getPrefix(line, i));
    const prefixWidth = Math.max(0, ...prefixes.map((p) => p.length));
    const summary = buildExportLineSummary(rawLines);
    const linesHtml = rawLines.map((rawLine, i) => {
      const line = lineEventFromWire(rawLine);
      const cls = lineLegacyClass(line);
      const prefix = prefixes[i];
      const prefixSpan = prefix ? `<span class="perm-prefix">${escapeExportHtml(prefix)}</span>` : "";
      const content = renderExportLineContent(line, ansiToHtml);
      return `<span class="line${cls ? " " + cls : ""}">${prefixSpan}<span class="perm-content">${content}</span></span>`;
    }).join("");
    return { linesHtml, prefixWidth, summary, summaryHtml: buildExportSummaryHtml(summary) };
  }
  function buildExportRunMetaItems(runMeta) {
    if (!runMeta) return [];
    const items = [];
    const { exitCode, duration, lines, version } = runMeta;
    if (exitCode !== null && exitCode !== void 0) {
      items.push({
        kind: "badge",
        tone: exitCode === 0 ? "ok" : "fail",
        text: `exit ${exitCode}`
      });
    }
    if (duration) items.push({ kind: "item", text: String(duration) });
    if (lines) items.push({ kind: "item", text: String(lines) });
    if (version) items.push({ kind: "item", text: `v${version}` });
    return items;
  }
  function buildExportHeaderModel({ appName, metaLine = "", runMeta = null }) {
    return {
      appName: String(appName || ""),
      metaLine: metaLine ? String(metaLine) : "",
      runMetaItems: buildExportRunMetaItems(runMeta)
    };
  }
  function buildExportRunMetaHtml(runMetaOrItems) {
    const items = Array.isArray(runMetaOrItems) ? runMetaOrItems : buildExportRunMetaItems(runMetaOrItems);
    return items.map((item) => {
      if (item.kind === "badge") {
        const cls = item.tone === "ok" ? "meta-badge-ok" : "meta-badge-fail";
        return `<span class="meta-badge ${cls}">${escapeExportHtml(item.text)}</span>`;
      }
      return `<span class="meta-item">${escapeExportHtml(item.text)}</span>`;
    }).join("");
  }
  function buildTerminalExportHeaderHtml(headerModel, { includeHighlightToggle = false } = {}) {
    const titleHtml = `<h1 class="export-title">${escapeExportHtml(headerModel.appName)}</h1>`;
    const metaHtml = headerModel.metaLine ? `<div class="export-meta">${escapeExportHtml(headerModel.metaLine)}</div>` : "";
    const runMetaHtml = headerModel.runMetaItems.length ? `<div class="export-run-meta">${buildExportRunMetaHtml(headerModel.runMetaItems)}</div>` : "";
    const actionsHtml = includeHighlightToggle ? `<div class="export-header-actions">
    <button type="button" class="export-highlight-toggle" data-export-toggle-highlights aria-pressed="true">highlights: on</button>
  </div>` : "";
    return `<header class="export-header">
  <div class="export-header-copy">
    ${titleHtml}
    ${metaHtml}
    ${runMetaHtml}
  </div>
  ${actionsHtml}
</header>`;
  }
  function buildTerminalExportScript() {
    return `<script>
(function () {
  var btn = document.querySelector('[data-export-toggle-highlights]');
  if (!btn) return;
  function sync() {
    var off = document.body.classList.contains('structured-highlights-off');
    btn.textContent = 'highlights: ' + (off ? 'off' : 'on');
    btn.setAttribute('aria-pressed', off ? 'false' : 'true');
  }
  btn.addEventListener('click', function () {
    document.body.classList.toggle('structured-highlights-off');
    sync();
  });
  sync();
}());
<\/script>`;
  }
  function buildTerminalExportStyles(fontFacesCss = "", prefixWidth = 0, exportCss = "") {
    const themeVars = getThemeExportVars();
    const themeDecls = Object.entries(themeVars).map(([name, value]) => `    ${name}: ${value};`).join("\n");
    return `${fontFacesCss}
  :root {
${themeDecls}
    --perm-prefix-width: ${prefixWidth}ch;
  }
  *, *::before, *::after { box-sizing: border-box; print-color-adjust: exact; -webkit-print-color-adjust: exact; }
  html, body { height: 100%; margin: 0; }
  body {
    display: flex;
    flex-direction: column;
    background: var(--bg);
    color: var(--text);
    font-family: 'JetBrains Mono', monospace;
    font-size: var(--terminal-font-size, 14px);
    line-height: var(--terminal-line-height, 1.65);
  }
  ${exportCss}`;
  }
  function buildTerminalExportHtml({
    appName,
    title,
    metaLine = "",
    runMeta = null,
    linesHtml = "",
    summaryHtml = "",
    prefixWidth = 0,
    fontFacesCss = "",
    exportCss = "",
    includeHighlightToggle = true,
    highlights = "on"
  }) {
    const colorScheme = getThemeExportColorScheme();
    const headerModel = buildExportHeaderModel({ appName, metaLine, runMeta });
    const styles = buildTerminalExportStyles(fontFacesCss, prefixWidth, exportCss);
    const bodyClass = highlights === "off" ? ' class="structured-highlights-off"' : "";
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="color-scheme" content="${escapeExportHtml(colorScheme)}">
<title>${escapeExportHtml(title)} — ${escapeExportHtml(appName)}</title>
<style>
${styles}
</style>
</head>
<body${bodyClass}>
${buildTerminalExportHeaderHtml(headerModel, { includeHighlightToggle })}
${summaryHtml || ""}
<main class="export-output nice-scroll">
${linesHtml}
</main>
${includeHighlightToggle ? buildTerminalExportScript() : ""}
</body>
</html>`;
  }
  let _cachedTerminalExportCss = null;
  async function fetchTerminalExportCss() {
    if (_cachedTerminalExportCss !== null) return _cachedTerminalExportCss;
    try {
      const res = await fetch("/static/css/terminal_export.css");
      _cachedTerminalExportCss = res.ok ? await res.text() : "";
    } catch (_) {
      _cachedTerminalExportCss = "";
    }
    return _cachedTerminalExportCss;
  }
  async function fetchVendorFontFacesCss() {
    const chunks = [];
    for (const font of EXPORT_FONT_FILES) {
      const res = await fetch(`/vendor/fonts/${font.filename}`);
      if (!res.ok) continue;
      const buf = await res.arrayBuffer();
      const bytes = new Uint8Array(buf);
      let binary = "";
      const chunkSize = 32768;
      for (let i = 0; i < bytes.length; i += chunkSize) {
        binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
      }
      const dataUrl = `url(data:font/ttf;base64,${btoa(binary)}) format('truetype')`;
      chunks.push(
        `@font-face { font-family: '${font.family}'; font-style: normal; font-weight: ${font.weight}; font-display: swap; src: ${dataUrl}; }`
      );
    }
    return chunks.join("\n");
  }
  window.ExportHtmlUtils = {
    exportTimestamp,
    buildExportMetaLine,
    normalizeExportTranscriptLine,
    normalizeExportTranscriptLines,
    appendCommandOutcomeSummaryLines,
    buildExportCommandOutcomeSummary,
    commandOutcomeSummaryToLines,
    isCommandOutcomeSummaryLine,
    normalizeExportRunMeta,
    lineEventFromWire,
    lineLegacyClass,
    isPromptEchoEvent,
    isPlainEvent,
    buildExportDocumentModel,
    escapeExportHtml,
    escapeExportAttr,
    renderExportPromptEcho,
    renderExportEntityContent,
    renderExportLineContent,
    buildExportLinesHtml,
    buildExportLineSummary,
    buildExportRunMetaItems,
    buildExportHeaderModel,
    buildExportRunMetaHtml,
    buildTerminalExportHeaderHtml,
    buildTerminalExportHtml,
    buildTerminalExportStyles,
    getThemeExportVars,
    getThemeExportColorScheme,
    fetchVendorFontFacesCss,
    fetchTerminalExportCss
  };
})();

// app/static/js/core/lazy_assets.js
(function() {
  const _lazyAssetPromises = {};
  let _lazyAssetConfigInvalidLogged = false;
  function _logLazyAssetConfigInvalid(err) {
    if (_lazyAssetConfigInvalidLogged || typeof window === "undefined" || typeof window.logClientError !== "function") return;
    _lazyAssetConfigInvalidLogged = true;
    window.logClientError("lazy asset config invalid", err, {
      event: "LAZY_ASSET_CONFIG_INVALID",
      level: "warning",
      source: "lazy-assets-json"
    });
  }
  function _lazyAssetConfig() {
    let urls = {};
    if (typeof document !== "undefined") {
      const node = document.getElementById("lazy-assets-json");
      if (node && node.textContent) {
        try {
          const parsed = JSON.parse(node.textContent);
          if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) urls = parsed;
        } catch (err) {
          _logLazyAssetConfigInvalid(err);
          urls = {};
        }
      }
    }
    const appConfigUrls = typeof window !== "undefined" && window.APP_CONFIG && window.APP_CONFIG.lazy_asset_urls;
    if (appConfigUrls && typeof appConfigUrls === "object" && !Array.isArray(appConfigUrls)) {
      urls = { ...urls, ...appConfigUrls };
    }
    return urls;
  }
  function _normalizeLazyAssetEntry(value) {
    if (typeof value === "string" && value) return { url: value, type: "classic" };
    if (value && typeof value === "object" && !Array.isArray(value)) {
      const url = typeof value.url === "string" ? value.url : "";
      const type = value.type === "module" ? "module" : "classic";
      if (url) return { url, type };
    }
    return { url: "", type: "classic" };
  }
  function _lazyAssetEntry(name) {
    const configured = _lazyAssetConfig()[name];
    const normalized = _normalizeLazyAssetEntry(configured);
    if (normalized.url) return normalized;
    if (name === "export_pdf") return { url: "/static/js/export_pdf.js", type: "module" };
    if (name === "atlas_tabs") return { url: "/static/js/features/atlas/atlas_tabs.js", type: "module" };
    if (name === "atlas_entity_row") return { url: "/static/js/features/atlas/atlas_entity_row.js", type: "module" };
    if (name === "atlas_entity_detail") return { url: "/static/js/features/atlas/atlas_entity_detail.js", type: "module" };
    if (name === "atlas_overlay") return { url: "/static/js/features/atlas/atlas_overlay.js", type: "module" };
    if (name === "atlas_mobile") return { url: "/static/js/features/atlas/atlas_mobile.js", type: "module" };
    if (name === "findings_board") return { url: "/static/js/features/findings/findings_board_modal.js", type: "module" };
    if (name === "project_activity") return { url: "/static/js/features/projects/project_activity.js", type: "module" };
    if (name === "project_artifacts") return { url: "/static/js/features/projects/project_artifacts.js", type: "module" };
    if (name === "project_details") return { url: "/static/js/features/projects/project_details.js", type: "module" };
    if (name === "project_list") return { url: "/static/js/features/projects/project_list.js", type: "module" };
    if (name === "project_navigation") return { url: "/static/js/features/projects/project_navigation.js", type: "module" };
    if (name === "project_entity_editor") return { url: "/static/js/features/projects/project_entity_editor.js", type: "module" };
    if (name === "project_workspace_actions") return { url: "/static/js/features/projects/project_workspace_actions.js", type: "module" };
    if (name === "project_workspace_shell") return { url: "/static/js/features/projects/project_workspace_shell.js", type: "module" };
    if (name === "project_workspace_lifecycle") return { url: "/static/js/features/projects/project_workspace_lifecycle.js", type: "module" };
    if (name === "project_workspace_renderer") return { url: "/static/js/features/projects/project_workspace_renderer.js", type: "module" };
    if (name === "project_workspace_bootstrap") return { url: "/static/js/features/projects/project_workspace_bootstrap.js", type: "module" };
    if (name === "project_nested_sheets") return { url: "/static/js/features/projects/project_nested_sheets.js", type: "module" };
    if (name === "project_workspace_events") return { url: "/static/js/features/projects/project_workspace_events.js", type: "module" };
    if (name === "project_targets") return { url: "/static/js/features/projects/project_targets.js", type: "module" };
    if (name === "project_runs") return { url: "/static/js/features/projects/project_runs.js", type: "module" };
    if (name === "project_mobile_compare") return { url: "/static/js/features/projects/project_mobile_compare.js", type: "module" };
    if (name === "project_mobile_shell") return { url: "/static/js/features/projects/project_mobile_shell.js", type: "module" };
    if (name === "project_mobile_detail") return { url: "/static/js/features/projects/project_mobile_detail.js", type: "module" };
    if (name === "project_findings_data") return { url: "/static/js/features/projects/project_findings_data.js", type: "module" };
    if (name === "project_filters") return { url: "/static/js/features/projects/project_filters.js", type: "module" };
    if (name === "project_entities") return { url: "/static/js/features/projects/project_entities.js", type: "module" };
    if (name === "project_findings") return { url: "/static/js/features/projects/project_findings.js", type: "module" };
    if (name === "project_findings_board") return { url: "/static/js/features/projects/project_findings_board.js", type: "module" };
    if (name === "project_packages") return { url: "/static/js/features/projects/project_packages.js", type: "module" };
    if (name === "project_report") return { url: "/static/js/features/projects/project_report.js", type: "module" };
    if (name === "history_compare_core") return { url: "/static/js/features/run-comparison/history_compare_core.js", type: "module" };
    if (name === "history_compare_overlay") return { url: "/static/js/features/run-comparison/history_compare_overlay.js", type: "module" };
    if (name === "history_compare_controls") return { url: "/static/js/features/run-comparison/history_compare_controls.js", type: "module" };
    if (name === "history_compare_navigation") return { url: "/static/js/features/run-comparison/history_compare_navigation.js", type: "module" };
    if (name === "history_compare_renderer") return { url: "/static/js/features/run-comparison/history_compare_renderer.js", type: "module" };
    if (name === "history_compare_launcher") return { url: "/static/js/features/run-comparison/history_compare_launcher.js", type: "module" };
    if (name === "history_run_details") return { url: "/static/js/features/history/history_run_details.js", type: "module" };
    if (name === "options_session_token_controls") return { url: "/static/js/features/preferences/session_token_controls.js", type: "module" };
    if (name === "options_secrets_panel") return { url: "/static/js/features/preferences/secrets_panel.js", type: "module" };
    if (name === "options_teams_panel") return { url: "/static/js/features/preferences/teams_panel.js", type: "module" };
    if (name === "options_notification_channels") return { url: "/static/js/features/preferences/notification_channels.js", type: "module" };
    if (name === "command_registry") return { url: "/static/js/features/command-registry/command_registry.js", type: "module" };
    if (name === "workflows") return { url: "/static/js/features/workflows/workflows.js", type: "module" };
    if (name === "pty_controller") return { url: "/static/js/pty.js", type: "module" };
    if (name === "schedules_modal") return { url: "/static/js/features/schedules/schedules_modal.js", type: "module" };
    if (name === "mobile_running_indicator") {
      return { url: "/static/js/features/mobile/mobile_running_indicator.js", type: "module" };
    }
    if (name === "tour_modal") return { url: "/static/js/tour_modal.js", type: "module" };
    if (name === "watchers_modal") return { url: "/static/js/features/watchers/watchers_modal.js", type: "module" };
    if (name === "status_monitor_core") return { url: "/static/js/features/status-monitor/status_monitor_core.js", type: "module" };
    if (name === "status_monitor_data") return { url: "/static/js/features/status-monitor/status_monitor_data.js", type: "module" };
    if (name === "status_monitor_resources") return { url: "/static/js/features/status-monitor/status_monitor_resources.js", type: "module" };
    if (name === "status_monitor") return { url: "/static/js/status_monitor.js", type: "module" };
    if (name === "jspdf") return { url: "/vendor/jspdf.umd.min.js", type: "classic" };
    if (name === "xterm_css") return { url: "/vendor/xterm.css", type: "classic" };
    if (name === "xterm_js") return { url: "/vendor/xterm.js", type: "classic" };
    if (name === "xterm_fit_js") return { url: "/vendor/xterm-addon-fit.js", type: "classic" };
    return { url: "", type: "classic" };
  }
  function _lazyAssetUrl(name) {
    return _lazyAssetEntry(name).url;
  }
  function _safeLazyAssetLogSrc(src) {
    const raw = String(src || "");
    if (!raw) return "";
    try {
      const parsed = new URL(raw, typeof window !== "undefined" && window.location ? window.location.href : "http://localhost/");
      const version = parsed.searchParams.get("v");
      return version ? `${parsed.pathname}?v=${encodeURIComponent(version)}` : parsed.pathname;
    } catch (_) {
      return raw.split("?", 1)[0].slice(0, 300);
    }
  }
  function _logLazyAssetLoadFailed(name, entry, err, globalCheck) {
    if (typeof window === "undefined" || typeof window.logClientError !== "function") return;
    window.logClientError("lazy asset load failed", err, {
      event: "LAZY_ASSET_LOAD_FAILED",
      level: "error",
      asset_name: String(name || "").slice(0, 120),
      asset_type: entry && entry.type === "module" ? "module" : "classic",
      src: _safeLazyAssetLogSrc(entry && entry.url),
      expected_global: typeof globalCheck === "function"
    });
  }
  function lazyAssetUrl(name) {
    return _lazyAssetUrl(name);
  }
  function loadLazyClassicScript(name, globalCheck) {
    if (typeof globalCheck === "function" && globalCheck()) return Promise.resolve();
    if (_lazyAssetPromises[name]) return _lazyAssetPromises[name];
    const entry = _lazyAssetEntry(name);
    const src = entry.url;
    if (!src) {
      const err = new Error(`Unknown lazy asset: ${name}`);
      _logLazyAssetLoadFailed(name, entry, err, globalCheck);
      return Promise.reject(err);
    }
    _lazyAssetPromises[name] = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = src;
      script.async = true;
      script.onload = () => {
        if (typeof globalCheck !== "function" || globalCheck()) resolve();
        else reject(new Error(`Lazy asset did not expose its expected global: ${src}`));
      };
      script.onerror = () => reject(new Error(`Failed to load lazy asset: ${src}`));
      (document.head || document.documentElement).appendChild(script);
    }).catch((err) => {
      delete _lazyAssetPromises[name];
      _logLazyAssetLoadFailed(name, entry, err, globalCheck);
      throw err;
    });
    return _lazyAssetPromises[name];
  }
  function loadLazyModule(name, globalCheck) {
    if (typeof globalCheck === "function" && globalCheck()) return Promise.resolve();
    if (_lazyAssetPromises[name]) return _lazyAssetPromises[name];
    const entry = _lazyAssetEntry(name);
    const src = entry.url;
    if (!src) {
      const err = new Error(`Unknown lazy asset: ${name}`);
      _logLazyAssetLoadFailed(name, entry, err, globalCheck);
      return Promise.reject(err);
    }
    const importer = typeof window !== "undefined" && typeof window.__darklabImportModule === "function" ? window.__darklabImportModule : (url) => import(url);
    _lazyAssetPromises[name] = Promise.resolve().then(() => importer(src)).then(() => {
      if (typeof globalCheck !== "function" || globalCheck()) return void 0;
      throw new Error(`Lazy module did not expose its expected global: ${src}`);
    }).catch((err) => {
      delete _lazyAssetPromises[name];
      _logLazyAssetLoadFailed(name, entry, err, globalCheck);
      throw err;
    });
    return _lazyAssetPromises[name];
  }
  function loadLazyAsset(name, globalCheck) {
    return _lazyAssetEntry(name).type === "module" ? loadLazyModule(name, globalCheck) : loadLazyClassicScript(name, globalCheck);
  }
  function loadLazyClassicScripts(items) {
    return items.reduce(
      (promise, item) => promise.then(() => loadLazyAsset(item.name, item.globalCheck)),
      Promise.resolve()
    );
  }
  async function loadJsPdf() {
    await loadLazyClassicScript("jspdf", () => !!(window.jspdf && window.jspdf.jsPDF));
    return window.jspdf.jsPDF;
  }
  async function loadExportPdfUtils() {
    await loadLazyAsset("export_pdf", () => !!(window.ExportPdfUtils && typeof window.ExportPdfUtils.buildTerminalExportPdf === "function"));
    return window.ExportPdfUtils;
  }
  async function loadFindingsBoard() {
    await loadLazyAsset("findings_board", () => !!(window.openFindingsBoard && window.openFindingsBoard !== lazyOpenFindingsBoard));
    return window.openFindingsBoard;
  }
  async function loadAtlasOverlay() {
    await loadLazyClassicScripts([
      {
        name: "atlas_tabs",
        globalCheck: () => !!window.DarklabAtlasTabs
      },
      {
        name: "atlas_entity_row",
        globalCheck: () => !!window.DarklabAtlasEntityRow
      },
      {
        name: "atlas_entity_detail",
        globalCheck: () => !!window.DarklabAtlasDetail
      },
      {
        name: "atlas_overlay",
        globalCheck: () => !!(window.openAtlas && window.openAtlas !== lazyOpenAtlas)
      },
      {
        name: "atlas_mobile",
        globalCheck: () => !!window.DarklabAtlasMobile || !document.getElementById("atlas-mobile-root")
      }
    ]);
    return window.openAtlas;
  }
  async function loadWatchersModal() {
    await loadLazyAsset("watchers_modal", () => !!(window.openWatchersModal && window.openWatchersModal !== lazyOpenWatchersModal));
    return window.openWatchersModal;
  }
  async function loadProjectReport() {
    await loadLazyAsset("project_report", () => !!(window.DarklabProjectReport && typeof window.DarklabProjectReport.createProjectReportController === "function"));
    return window.DarklabProjectReport;
  }
  async function loadProjectActivity() {
    await loadLazyAsset("project_activity", () => !!(window.DarklabProjectActivity && typeof window.DarklabProjectActivity.createProjectActivityController === "function"));
    return window.DarklabProjectActivity;
  }
  async function loadProjectArtifacts() {
    await loadLazyAsset("project_artifacts", () => !!(window.DarklabProjectArtifacts && typeof window.DarklabProjectArtifacts.createProjectArtifactsController === "function"));
    return window.DarklabProjectArtifacts;
  }
  async function loadProjectPackages() {
    await loadLazyAsset("project_packages", () => !!(window.DarklabProjectPackages && typeof window.DarklabProjectPackages.createProjectPackagesController === "function"));
    return window.DarklabProjectPackages;
  }
  async function loadProjectWorkspace() {
    await loadLazyClassicScripts([
      {
        name: "project_details",
        globalCheck: () => !!(window.DarklabProjectDetails && typeof window.DarklabProjectDetails.createProjectDetailsController === "function")
      },
      {
        name: "project_list",
        globalCheck: () => !!(window.DarklabProjectList && typeof window.DarklabProjectList.createProjectListController === "function")
      },
      {
        name: "project_navigation",
        globalCheck: () => !!(window.DarklabProjectNavigation && typeof window.DarklabProjectNavigation.createProjectNavigationController === "function")
      },
      {
        name: "project_entity_editor",
        globalCheck: () => !!(window.DarklabProjectEntityEditor && typeof window.DarklabProjectEntityEditor.createProjectEntityEditorController === "function")
      },
      {
        name: "project_workspace_actions",
        globalCheck: () => !!(window.DarklabProjectWorkspaceActions && typeof window.DarklabProjectWorkspaceActions.createProjectWorkspaceActionsController === "function")
      },
      {
        name: "project_workspace_shell",
        globalCheck: () => !!(window.DarklabProjectWorkspaceShell && typeof window.DarklabProjectWorkspaceShell.createProjectWorkspaceShellController === "function")
      },
      {
        name: "project_workspace_lifecycle",
        globalCheck: () => !!(window.DarklabProjectWorkspaceLifecycle && typeof window.DarklabProjectWorkspaceLifecycle.createProjectWorkspaceLifecycleController === "function")
      },
      {
        name: "project_workspace_renderer",
        globalCheck: () => !!(window.DarklabProjectWorkspaceRenderer && typeof window.DarklabProjectWorkspaceRenderer.createProjectWorkspaceRendererController === "function")
      },
      {
        name: "project_workspace_bootstrap",
        globalCheck: () => !!(window.DarklabProjectWorkspaceBootstrap && typeof window.DarklabProjectWorkspaceBootstrap.createProjectWorkspaceBootstrapController === "function")
      },
      {
        name: "project_nested_sheets",
        globalCheck: () => !!(window.DarklabProjectNestedSheets && typeof window.DarklabProjectNestedSheets.createProjectNestedSheetsController === "function")
      },
      {
        name: "project_workspace_events",
        globalCheck: () => !!(window.DarklabProjectWorkspaceEvents && typeof window.DarklabProjectWorkspaceEvents.createProjectWorkspaceEventsController === "function")
      },
      {
        name: "project_targets",
        globalCheck: () => !!(window.DarklabProjectTargets && typeof window.DarklabProjectTargets.createProjectTargetsController === "function")
      },
      {
        name: "project_runs",
        globalCheck: () => !!(window.DarklabProjectRuns && typeof window.DarklabProjectRuns.createProjectRunsController === "function")
      },
      {
        name: "project_mobile_compare",
        globalCheck: () => !!(window.DarklabProjectMobileCompare && typeof window.DarklabProjectMobileCompare.createProjectMobileCompareController === "function")
      },
      {
        name: "project_mobile_shell",
        globalCheck: () => !!(window.DarklabProjectMobileShell && typeof window.DarklabProjectMobileShell.createProjectMobileShellController === "function")
      },
      {
        name: "project_mobile_detail",
        globalCheck: () => !!(window.DarklabProjectMobileDetail && typeof window.DarklabProjectMobileDetail.createProjectMobileDetailController === "function")
      },
      {
        name: "project_findings_data",
        globalCheck: () => !!(window.DarklabProjectFindingsData && typeof window.DarklabProjectFindingsData.createProjectFindingsDataController === "function")
      },
      {
        name: "project_filters",
        globalCheck: () => !!(window.DarklabProjectFilters && typeof window.DarklabProjectFilters.createProjectFiltersController === "function")
      },
      {
        name: "project_entities",
        globalCheck: () => !!(window.DarklabProjectEntities && typeof window.DarklabProjectEntities.createProjectEntitiesController === "function")
      },
      {
        name: "project_findings",
        globalCheck: () => !!(window.DarklabProjectFindings && typeof window.DarklabProjectFindings.createProjectFindingsController === "function")
      },
      {
        name: "project_findings_board",
        globalCheck: () => !!(window.DarklabProjectFindingsBoard && typeof window.DarklabProjectFindingsBoard.createProjectFindingsBoardController === "function")
      }
    ]);
    return window.DarklabProjectWorkspaceShell;
  }
  async function loadHistoryRunDetails() {
    await loadLazyAsset("history_run_details", () => !!(window.openHistoryRunDetails && window.openHistoryRunDetails !== lazyOpenHistoryRunDetails));
    return window.openHistoryRunDetails;
  }
  async function loadOptionsPanels() {
    await loadLazyClassicScripts([
      {
        name: "options_session_token_controls",
        globalCheck: () => typeof window._updateOptionsSessionTokenStatus === "function"
      },
      {
        name: "options_secrets_panel",
        globalCheck: () => !!(window.refreshOptionsSecrets && window.refreshOptionsSecrets !== lazyRefreshOptionsSecrets && window.invalidateOptionsSecrets && window.invalidateOptionsSecrets !== lazyInvalidateOptionsSecrets)
      },
      {
        name: "options_teams_panel",
        globalCheck: () => !!(window.refreshOptionsTeams && window.refreshOptionsTeams !== lazyRefreshOptionsTeams)
      },
      {
        name: "options_notification_channels",
        globalCheck: () => !!(window.refreshNotificationChannels && window.refreshNotificationChannels !== lazyRefreshNotificationChannels)
      }
    ]);
    return true;
  }
  async function loadCommandRegistry() {
    await loadLazyAsset("command_registry", () => !!(window.openCommandRegistry && window.openCommandRegistry !== lazyOpenCommandRegistry));
    return window.openCommandRegistry;
  }
  async function loadWorkflows() {
    await loadLazyAsset("workflows", () => !!(window.renderWorkflowItems && window.renderWorkflowItems !== lazyRenderWorkflowItems && window.handleWorkflowTerminalCommand && window.handleWorkflowTerminalCommand !== lazyHandleWorkflowTerminalCommand));
    return true;
  }
  async function lazyOpenWorkflowEditor(workflow = null) {
    await loadWorkflows();
    if (typeof window.openWorkflowEditor !== "function" || window.openWorkflowEditor === lazyOpenWorkflowEditor) {
      return false;
    }
    return window.openWorkflowEditor(workflow);
  }
  async function loadHistoryCompare() {
    await loadLazyClassicScripts([
      {
        name: "history_compare_core",
        globalCheck: () => !!window.DarklabHistoryCompareCore
      },
      {
        name: "history_compare_overlay",
        globalCheck: () => !!(window.closeHistoryCompareOverlay && window.closeHistoryCompareOverlay !== lazyCloseHistoryCompareOverlay && window.isHistoryCompareOverlayOpen && window.isHistoryCompareOverlayOpen !== lazyIsHistoryCompareOverlayOpen)
      },
      {
        name: "history_compare_controls",
        globalCheck: () => typeof window._closeHistoryCompareActionMenus === "function"
      },
      {
        name: "history_compare_navigation",
        globalCheck: () => typeof window._historyCompareScrollToLine === "function"
      },
      {
        name: "history_compare_renderer",
        globalCheck: () => !!(window.fetchAndRenderHistoryComparison && window.fetchAndRenderHistoryComparison !== lazyFetchAndRenderHistoryComparison)
      },
      {
        name: "history_compare_launcher",
        globalCheck: () => !!(window.openHistoryCompareLauncher && window.openHistoryCompareLauncher !== lazyOpenHistoryCompareLauncher)
      }
    ]);
    return window.openHistoryCompareLauncher;
  }
  async function loadPtyController() {
    await loadLazyAsset("pty_controller", () => !!(window.startInteractivePtyCommand && window.startInteractivePtyCommand !== lazyStartInteractivePtyCommand && window.attachInteractivePtyCommand && window.attachInteractivePtyCommand !== lazyAttachInteractivePtyCommand && typeof window.isInteractivePtyCommand === "function"));
    return window.startInteractivePtyCommand;
  }
  async function loadPtyAttachController() {
    await loadPtyController();
    return window.attachInteractivePtyCommand;
  }
  async function loadSchedulesModal() {
    await loadLazyAsset("schedules_modal", () => !!(window.openSchedulesModal && window.openSchedulesModal !== lazyOpenSchedulesModal));
    return window.openSchedulesModal;
  }
  async function loadTourModal() {
    await loadLazyAsset("tour_modal", () => !!(window.openTourModal && window.openTourModal !== lazyOpenTourModal));
    return window.openTourModal;
  }
  async function loadStatusMonitor() {
    await loadLazyClassicScripts([
      {
        name: "status_monitor_core",
        globalCheck: () => !!window.DarklabStatusMonitorCore
      },
      {
        name: "status_monitor_data",
        globalCheck: () => !!window.DarklabStatusMonitorData
      },
      {
        name: "status_monitor_resources",
        globalCheck: () => !!window.DarklabStatusMonitorResources
      },
      {
        name: "status_monitor",
        globalCheck: () => !!(window.openStatusMonitor && window.openStatusMonitor !== lazyOpenStatusMonitor)
      }
    ]);
    return window.openStatusMonitor;
  }
  async function lazyOpenFindingsBoard(options = {}) {
    const open = await loadFindingsBoard();
    if (typeof open !== "function" || open === lazyOpenFindingsBoard) return false;
    return open(options);
  }
  async function lazyOpenAtlas(options = {}) {
    const open = await loadAtlasOverlay();
    if (typeof open !== "function" || open === lazyOpenAtlas) return false;
    return open(options);
  }
  function lazyCloseAtlas(options = {}) {
    if (window.closeAtlas === lazyCloseAtlas) return false;
    if (typeof window.closeAtlas === "function") return window.closeAtlas(options);
    return false;
  }
  function lazyIsAtlasOverlayOpen() {
    if (window.isAtlasOverlayOpen === lazyIsAtlasOverlayOpen) {
      const overlay = document.getElementById("atlas-overlay");
      return !!(overlay && overlay.classList.contains("open"));
    }
    if (typeof window.isAtlasOverlayOpen === "function") return window.isAtlasOverlayOpen();
    return false;
  }
  function lazyCycleAtlasTab(offset) {
    if (window.cycleAtlasTab === lazyCycleAtlasTab) return false;
    if (typeof window.cycleAtlasTab === "function") return window.cycleAtlasTab(offset);
    return false;
  }
  function lazyCloseFindingsBoard(options = {}) {
    if (window.closeFindingsBoard === lazyCloseFindingsBoard) return false;
    if (typeof window.closeFindingsBoard === "function") return window.closeFindingsBoard(options);
    return false;
  }
  async function lazyOpenWatchersModal(options = {}) {
    const open = await loadWatchersModal();
    if (typeof open !== "function" || open === lazyOpenWatchersModal) return false;
    return open(options);
  }
  function lazyCloseWatchersModal(options = {}) {
    if (window.closeWatchersModal === lazyCloseWatchersModal) return false;
    if (typeof window.closeWatchersModal === "function") return window.closeWatchersModal(options);
    return false;
  }
  async function lazyOpenSchedulesModal(options = {}) {
    const open = await loadSchedulesModal();
    if (typeof open !== "function" || open === lazyOpenSchedulesModal) return false;
    return open(options);
  }
  function lazyCloseSchedulesModal(options = {}) {
    if (window.closeSchedulesModal === lazyCloseSchedulesModal) return false;
    if (typeof window.closeSchedulesModal === "function") return window.closeSchedulesModal(options);
    return false;
  }
  async function lazyOpenTourModal(options = {}) {
    const open = await loadTourModal();
    if (typeof open !== "function" || open === lazyOpenTourModal) return false;
    return open(options);
  }
  function lazyCloseTourModal(options = {}) {
    if (window.closeTourModal === lazyCloseTourModal) return false;
    if (typeof window.closeTourModal === "function") return window.closeTourModal(options);
    return false;
  }
  async function lazyOpenStatusMonitor(options = {}) {
    const open = await loadStatusMonitor();
    if (typeof open !== "function" || open === lazyOpenStatusMonitor) return false;
    return open(options);
  }
  async function lazyOpenHistoryRunDetails(run) {
    const open = await loadHistoryRunDetails();
    if (typeof open !== "function" || open === lazyOpenHistoryRunDetails) return false;
    return open(run);
  }
  async function lazyRefreshOptionsSecrets(options = {}) {
    await loadOptionsPanels();
    if (typeof window.refreshOptionsSecrets !== "function" || window.refreshOptionsSecrets === lazyRefreshOptionsSecrets) {
      return false;
    }
    return window.refreshOptionsSecrets(options);
  }
  async function lazyRefreshOptionsTeams(options = {}) {
    await loadOptionsPanels();
    if (typeof window.refreshOptionsTeams !== "function" || window.refreshOptionsTeams === lazyRefreshOptionsTeams) {
      return false;
    }
    return window.refreshOptionsTeams(options);
  }
  async function lazyRefreshNotificationChannels(options = {}) {
    await loadOptionsPanels();
    if (typeof window.refreshNotificationChannels !== "function" || window.refreshNotificationChannels === lazyRefreshNotificationChannels) {
      return false;
    }
    return window.refreshNotificationChannels(options);
  }
  function lazyInvalidateOptionsSecrets() {
    if (window.invalidateOptionsSecrets === lazyInvalidateOptionsSecrets) return false;
    if (typeof window.invalidateOptionsSecrets === "function") return window.invalidateOptionsSecrets();
    return false;
  }
  async function lazyOpenCommandRegistry() {
    const open = await loadCommandRegistry();
    if (typeof open !== "function" || open === lazyOpenCommandRegistry) return false;
    return open();
  }
  function lazyCloseCommandRegistry() {
    if (window.closeCommandRegistry === lazyCloseCommandRegistry) return false;
    if (typeof window.closeCommandRegistry === "function") return window.closeCommandRegistry();
    if (typeof window.hideCommandRegistryOverlay === "function") return window.hideCommandRegistryOverlay();
    return false;
  }
  function lazyHideCommandRegistryOverlay() {
    const overlay = document.getElementById("command-registry-overlay");
    if (!overlay) return false;
    overlay.classList.add("u-hidden");
    overlay.classList.remove("open");
    overlay.setAttribute("aria-hidden", "true");
    return true;
  }
  function lazyIsCommandRegistryOverlayOpen() {
    if (window.isCommandRegistryOverlayOpen === lazyIsCommandRegistryOverlayOpen) {
      const overlay = document.getElementById("command-registry-overlay");
      return !!(overlay && overlay.classList.contains("open"));
    }
    if (typeof window.isCommandRegistryOverlayOpen === "function") return window.isCommandRegistryOverlayOpen();
    return false;
  }
  function _workflowCachedItems() {
    return Array.isArray(window.__workflowCatalogItems) ? window.__workflowCatalogItems : [];
  }
  function _setWorkflowCachedItems(items) {
    window.__workflowCatalogItems = Array.isArray(items) ? items.slice() : [];
    return window.__workflowCatalogItems;
  }
  function _emitWorkflowCatalog(items) {
    if (typeof window.emitUiEvent === "function") {
      window.emitUiEvent("app:workflows-rendered", {
        count: items.length,
        items: items.slice()
      });
    }
  }
  let _workflowCatalogLoadPromise = null;
  function lazyRenderWorkflowItems(items, options = {}) {
    const nextItems = _setWorkflowCachedItems(items);
    if (options.emitCatalogEvent !== false) _emitWorkflowCatalog(nextItems);
    return nextItems;
  }
  async function lazyReloadWorkflowCatalog() {
    if (_workflowCatalogLoadPromise) return _workflowCatalogLoadPromise;
    if (typeof window.apiFetch !== "function") return _workflowCachedItems();
    _workflowCatalogLoadPromise = (async () => {
      const resp = await window.apiFetch("/workflows");
      if (resp && resp.ok === false) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      return lazyRenderWorkflowItems(data.items || []);
    })();
    try {
      return await _workflowCatalogLoadPromise;
    } finally {
      _workflowCatalogLoadPromise = null;
    }
  }
  function lazyEnsureWorkflowCatalogLoaded() {
    const items = _workflowCachedItems();
    if (items.length) return Promise.resolve(items);
    return lazyReloadWorkflowCatalog();
  }
  async function lazyHandleWorkflowTerminalCommand(cmd, tabId) {
    await loadWorkflows();
    if (typeof window.handleWorkflowTerminalCommand !== "function" || window.handleWorkflowTerminalCommand === lazyHandleWorkflowTerminalCommand) {
      return false;
    }
    return window.handleWorkflowTerminalCommand(cmd, tabId);
  }
  async function lazyOpenHistoryCompareLauncher(run) {
    const open = await loadHistoryCompare();
    if (typeof open !== "function" || open === lazyOpenHistoryCompareLauncher) return false;
    return open(run);
  }
  async function lazyFetchAndRenderHistoryComparison(leftId, rightId, options = {}) {
    await loadHistoryCompare();
    if (typeof window.fetchAndRenderHistoryComparison !== "function" || window.fetchAndRenderHistoryComparison === lazyFetchAndRenderHistoryComparison) {
      return false;
    }
    return window.fetchAndRenderHistoryComparison(leftId, rightId, options);
  }
  function lazyCloseHistoryCompareOverlay(options = {}) {
    if (window.closeHistoryCompareOverlay === lazyCloseHistoryCompareOverlay) return false;
    if (typeof window.closeHistoryCompareOverlay === "function") return window.closeHistoryCompareOverlay(options);
    return false;
  }
  function lazyIsHistoryCompareOverlayOpen() {
    if (window.isHistoryCompareOverlayOpen === lazyIsHistoryCompareOverlayOpen) {
      const overlay = document.getElementById("history-compare-overlay");
      return !!(overlay && !overlay.classList.contains("u-hidden"));
    }
    if (typeof window.isHistoryCompareOverlayOpen === "function") return window.isHistoryCompareOverlayOpen();
    return false;
  }
  function lazyCloseStatusMonitor(options = {}) {
    if (window.closeStatusMonitor === lazyCloseStatusMonitor) return false;
    if (typeof window.closeStatusMonitor === "function") return window.closeStatusMonitor(options);
    return false;
  }
  function lazyIsStatusMonitorOpen() {
    if (window.isStatusMonitorOpen === lazyIsStatusMonitorOpen) return false;
    if (typeof window.isStatusMonitorOpen === "function") return window.isStatusMonitorOpen();
    const monitor = document.getElementById("status-monitor");
    return !!(monitor && !monitor.classList.contains("u-hidden"));
  }
  function _splitInteractivePtyCommand(cmd) {
    return String(cmd || "").trim().match(/"[^"]*"|'[^']*'|\S+/g) || [];
  }
  function _interactivePtySpecs() {
    const configured = window.APP_CONFIG && Array.isArray(window.APP_CONFIG.interactive_pty_commands) ? window.APP_CONFIG.interactive_pty_commands : [];
    if (configured.length) return configured;
    return [{ root: "mtr", trigger_flag: "--interactive" }];
  }
  function lazyIsInteractivePtyCommand(cmd) {
    const parts = _splitInteractivePtyCommand(cmd);
    const root = String(parts[0] || "").toLowerCase();
    if (!root) return false;
    return _interactivePtySpecs().some((spec) => {
      const specRoot = String(spec && spec.root || "").toLowerCase();
      const trigger = String(spec && spec.trigger_flag || "");
      return specRoot === root && !!trigger && parts.slice(1).includes(trigger);
    });
  }
  async function lazyStartInteractivePtyCommand(cmd, tabId) {
    const start = await loadPtyController();
    if (typeof start !== "function" || start === lazyStartInteractivePtyCommand) return false;
    return start(cmd, tabId);
  }
  async function lazyAttachInteractivePtyCommand(runOrRunId, tabId = "") {
    const attach = await loadPtyAttachController();
    if (typeof attach !== "function" || attach === lazyAttachInteractivePtyCommand) return false;
    return attach(runOrRunId, tabId);
  }
  window.loadLazyClassicScript = loadLazyClassicScript;
  window.loadLazyModule = loadLazyModule;
  window.loadLazyAsset = loadLazyAsset;
  window.lazyAssetUrl = lazyAssetUrl;
  window.loadJsPdf = loadJsPdf;
  window.loadLazyClassicScripts = loadLazyClassicScripts;
  window.loadExportPdfUtils = loadExportPdfUtils;
  window.loadAtlasOverlay = loadAtlasOverlay;
  window.loadFindingsBoard = loadFindingsBoard;
  window.loadProjectActivity = loadProjectActivity;
  window.loadProjectArtifacts = loadProjectArtifacts;
  window.loadProjectWorkspace = loadProjectWorkspace;
  window.loadProjectPackages = loadProjectPackages;
  window.loadProjectReport = loadProjectReport;
  window.loadHistoryCompare = loadHistoryCompare;
  window.loadHistoryRunDetails = loadHistoryRunDetails;
  window.loadOptionsPanels = loadOptionsPanels;
  window.loadCommandRegistry = loadCommandRegistry;
  window.loadWorkflows = loadWorkflows;
  window.loadPtyController = loadPtyController;
  window.loadPtyAttachController = loadPtyAttachController;
  window.loadWatchersModal = loadWatchersModal;
  window.loadSchedulesModal = loadSchedulesModal;
  window.loadTourModal = loadTourModal;
  window.loadStatusMonitor = loadStatusMonitor;
  if (typeof window.openAtlas !== "function") window.openAtlas = lazyOpenAtlas;
  if (typeof window.closeAtlas !== "function") window.closeAtlas = lazyCloseAtlas;
  if (typeof window.isAtlasOverlayOpen !== "function") window.isAtlasOverlayOpen = lazyIsAtlasOverlayOpen;
  if (typeof window.cycleAtlasTab !== "function") window.cycleAtlasTab = lazyCycleAtlasTab;
  if (typeof window.openFindingsBoard !== "function") window.openFindingsBoard = lazyOpenFindingsBoard;
  if (typeof window.closeFindingsBoard !== "function") window.closeFindingsBoard = lazyCloseFindingsBoard;
  if (typeof window.openSchedulesModal !== "function") window.openSchedulesModal = lazyOpenSchedulesModal;
  if (typeof window.closeSchedulesModal !== "function") window.closeSchedulesModal = lazyCloseSchedulesModal;
  if (typeof window.openTourModal !== "function") window.openTourModal = lazyOpenTourModal;
  if (typeof window.closeTourModal !== "function") window.closeTourModal = lazyCloseTourModal;
  if (typeof window.openStatusMonitor !== "function") window.openStatusMonitor = lazyOpenStatusMonitor;
  if (typeof window.closeStatusMonitor !== "function") window.closeStatusMonitor = lazyCloseStatusMonitor;
  if (typeof window.isStatusMonitorOpen !== "function") window.isStatusMonitorOpen = lazyIsStatusMonitorOpen;
  if (typeof window.openWatchersModal !== "function") window.openWatchersModal = lazyOpenWatchersModal;
  if (typeof window.closeWatchersModal !== "function") window.closeWatchersModal = lazyCloseWatchersModal;
  if (typeof window.openHistoryCompareLauncher !== "function") window.openHistoryCompareLauncher = lazyOpenHistoryCompareLauncher;
  if (typeof window.fetchAndRenderHistoryComparison !== "function") window.fetchAndRenderHistoryComparison = lazyFetchAndRenderHistoryComparison;
  if (typeof window.closeHistoryCompareOverlay !== "function") window.closeHistoryCompareOverlay = lazyCloseHistoryCompareOverlay;
  if (typeof window.isHistoryCompareOverlayOpen !== "function") window.isHistoryCompareOverlayOpen = lazyIsHistoryCompareOverlayOpen;
  if (typeof window.openHistoryRunDetails !== "function") window.openHistoryRunDetails = lazyOpenHistoryRunDetails;
  if (typeof window.refreshOptionsSecrets !== "function") window.refreshOptionsSecrets = lazyRefreshOptionsSecrets;
  if (typeof window.invalidateOptionsSecrets !== "function") window.invalidateOptionsSecrets = lazyInvalidateOptionsSecrets;
  if (typeof window.refreshOptionsTeams !== "function") window.refreshOptionsTeams = lazyRefreshOptionsTeams;
  if (typeof window.refreshNotificationChannels !== "function") window.refreshNotificationChannels = lazyRefreshNotificationChannels;
  if (typeof window.openCommandRegistry !== "function") window.openCommandRegistry = lazyOpenCommandRegistry;
  if (typeof window.closeCommandRegistry !== "function") window.closeCommandRegistry = lazyCloseCommandRegistry;
  if (typeof window.hideCommandRegistryOverlay !== "function") window.hideCommandRegistryOverlay = lazyHideCommandRegistryOverlay;
  if (typeof window.isCommandRegistryOverlayOpen !== "function") {
    window.isCommandRegistryOverlayOpen = lazyIsCommandRegistryOverlayOpen;
  }
  if (typeof window.renderWorkflowItems !== "function") window.renderWorkflowItems = lazyRenderWorkflowItems;
  if (typeof window.reloadWorkflowCatalog !== "function") window.reloadWorkflowCatalog = lazyReloadWorkflowCatalog;
  if (typeof window.ensureWorkflowCatalogLoaded !== "function") {
    window.ensureWorkflowCatalogLoaded = lazyEnsureWorkflowCatalogLoaded;
  }
  if (typeof window.handleWorkflowTerminalCommand !== "function") {
    window.handleWorkflowTerminalCommand = lazyHandleWorkflowTerminalCommand;
  }
  if (typeof window.openWorkflowEditor !== "function") window.openWorkflowEditor = lazyOpenWorkflowEditor;
  if (typeof window.isInteractivePtyCommand !== "function") window.isInteractivePtyCommand = lazyIsInteractivePtyCommand;
  if (typeof window.startInteractivePtyCommand !== "function") window.startInteractivePtyCommand = lazyStartInteractivePtyCommand;
  if (typeof window.attachInteractivePtyCommand !== "function") window.attachInteractivePtyCommand = lazyAttachInteractivePtyCommand;
})();

// app/static/js/ui/ui_outside_click.js
(function(global) {
  "use strict";
  function _toArray(input) {
    if (!input) return [];
    if (Array.isArray(input)) return input.filter(Boolean);
    return [input];
  }
  function bindOutsideClickClose2(panel, opts) {
    if (!opts) return null;
    if (typeof opts.isOpen !== "function") return null;
    if (typeof opts.onClose !== "function") return null;
    const isOpenFn = opts.isOpen;
    const onCloseFn = opts.onClose;
    const triggers = _toArray(opts.triggers);
    const exemptSelectors = _toArray(opts.exemptSelectors);
    const scope = opts.scope || (typeof document !== "undefined" ? document : null);
    const capture = !!opts.capture;
    if (!scope || typeof scope.addEventListener !== "function") return null;
    const handler = (e) => {
      if (!isOpenFn()) return;
      const target = e.target;
      if (!target) return;
      if (panel && panel.contains && panel.contains(target)) return;
      for (let i = 0; i < triggers.length; i += 1) {
        const t = triggers[i];
        if (!t) continue;
        if (t === target) return;
        if (t.contains && t.contains(target)) return;
      }
      if (exemptSelectors.length && typeof target.closest === "function") {
        for (let i = 0; i < exemptSelectors.length; i += 1) {
          if (target.closest(exemptSelectors[i])) return;
        }
      }
      onCloseFn();
    };
    scope.addEventListener("click", handler, capture);
    return {
      dispose: () => {
        scope.removeEventListener("click", handler, capture);
      }
    };
  }
  global.bindOutsideClickClose = bindOutsideClickClose2;
})(typeof window !== "undefined" ? window : globalThis);

// app/static/js/permalink.js
(function() {
  var exportHtmlUtils = window.ExportHtmlUtils || (typeof ExportHtmlUtils !== "undefined" ? ExportHtmlUtils : {});
  var AnsiUpCtor = window.AnsiUp || (typeof AnsiUp !== "undefined" ? AnsiUp : null);
  var bindOutsideClickCloseFn = window.bindOutsideClickClose || (typeof bindOutsideClickClose !== "undefined" ? bindOutsideClickClose : null);
  var copyTextToClipboardFn = window.copyTextToClipboard || (typeof copyTextToClipboard !== "undefined" ? copyTextToClipboard : null);
  var downloadBlobAsAttachmentFn = window.downloadBlobAsAttachment || (typeof downloadBlobAsAttachment !== "undefined" ? downloadBlobAsAttachment : null);
  var showToastFn = window.showToast || (typeof showToast !== "undefined" ? showToast : null);
  var pd = window.PermData || {};
  var transcriptModel = pd.transcript || {};
  var exportModel = pd.export || {};
  var headerModel = pd.header || {};
  var rawLines = typeof exportHtmlUtils.normalizeExportTranscriptLines === "function" ? exportHtmlUtils.normalizeExportTranscriptLines(transcriptModel.lines || pd.lines || []) : transcriptModel.lines || pd.lines || [];
  var hasTimestampMetadata = transcriptModel.hasTimestampMetadata || pd.hasTimestampMetadata || false;
  var appName = exportModel.appName || pd.appName || headerModel.appName || "";
  var label = exportModel.label || pd.label || "";
  var command = exportModel.command || transcriptModel.command || pd.command || label;
  var created = exportModel.created || pd.created || "";
  var createdDisplay = exportModel.createdDisplay || pd.createdDisplay || headerModel.createdDisplay || "";
  var fontFacesCss = exportModel.fontFacesCss || pd.fontFacesCss || "";
  var permalinkMeta = typeof exportHtmlUtils.normalizeExportRunMeta === "function" ? exportHtmlUtils.normalizeExportRunMeta(exportModel.runMeta || pd.permalinkMeta || null) : exportModel.runMeta || pd.permalinkMeta || null;
  var ansiUp = new AnsiUpCtor();
  ansiUp.use_classes = false;
  var out = document.getElementById("output");
  var tsModes = ["off", "elapsed", "clock"];
  function getCookie(name) {
    var prefix = name + "=";
    var match = document.cookie.split(";").map(function(p) {
      return p.trim();
    }).find(function(p) {
      return p.startsWith(prefix);
    });
    return match ? decodeURIComponent(match.slice(prefix.length)) : "";
  }
  var lnMode = getCookie("pref_line_numbers") === "on" ? "on" : "off";
  var tsMode = tsModes.includes(getCookie("pref_timestamps")) ? getCookie("pref_timestamps") : "off";
  var highlightMode = getCookie("pref_structured_highlights") === "off" ? "off" : "on";
  var commandOutcomeSummariesEnabled = getCookie("pref_command_outcome_summaries") !== "off";
  var lines = typeof exportHtmlUtils.appendCommandOutcomeSummaryLines === "function" ? exportHtmlUtils.appendCommandOutcomeSummaryLines(rawLines, { command, enabled: commandOutcomeSummariesEnabled }) : rawLines;
  if (!hasTimestampMetadata) tsMode = "off";
  function setCookie(name, value) {
    document.cookie = name + "=" + encodeURIComponent(value) + "; path=/; max-age=31536000; SameSite=Lax";
  }
  function syncHighlightMode() {
    document.body.classList.toggle("structured-highlights-off", highlightMode === "off");
    var highlightBtn = document.getElementById("toggle-highlights");
    if (highlightBtn) {
      highlightBtn.textContent = "highlights: " + highlightMode;
      highlightBtn.setAttribute("aria-pressed", highlightMode === "on" ? "true" : "false");
    }
  }
  function timestampText(entry) {
    if (tsMode === "clock") return entry.tsC || "";
    if (tsMode === "elapsed") return entry.tsE || "";
    return "";
  }
  function formatPrefix(index, entry) {
    if (typeof exportHtmlUtils.isCommandOutcomeSummaryLine === "function" && exportHtmlUtils.isCommandOutcomeSummaryLine(entry)) {
      return "";
    }
    var parts = [];
    if (lnMode === "on") parts.push(String(index));
    var ts = timestampText(entry);
    if (ts) parts.push(ts);
    return parts.join(" ");
  }
  function displayText(entry, index) {
    var prefix = formatPrefix(index + 1, entry);
    return (prefix ? prefix + "  " : "") + String(entry.text || "");
  }
  function renderOutput() {
    out.innerHTML = "";
    var prefixes = lines.map(function(entry, index) {
      return formatPrefix(index + 1, entry);
    });
    var prefixWidth = Math.max(0, Math.max.apply(null, prefixes.map(function(p) {
      return p.length;
    })));
    out.style.setProperty("--perm-prefix-width", prefixWidth + "ch");
    lines.forEach(function(entry, index) {
      var lineEvent = exportHtmlUtils.lineEventFromWire(entry);
      var span = document.createElement("span");
      var cls = exportHtmlUtils.lineLegacyClass(lineEvent);
      span.className = "line" + (cls ? " " + cls : "");
      var prefix = prefixes[index];
      if (prefix) {
        var prefixEl = document.createElement("span");
        prefixEl.className = "perm-prefix";
        prefixEl.textContent = prefix;
        span.appendChild(prefixEl);
      }
      var contentEl = document.createElement("span");
      contentEl.className = "perm-content";
      if (typeof exportHtmlUtils.renderExportLineContent === "function") {
        contentEl.innerHTML = exportHtmlUtils.renderExportLineContent(lineEvent, function(text) {
          return ansiUp.ansi_to_html(text);
        });
      } else if (exportHtmlUtils.isPromptEchoEvent(lineEvent)) {
        contentEl.innerHTML = exportHtmlUtils.renderExportPromptEcho(lineEvent.text);
      } else if (exportHtmlUtils.isPlainEvent(lineEvent)) {
        contentEl.textContent = lineEvent.text;
      } else {
        contentEl.innerHTML = ansiUp.ansi_to_html(lineEvent.text);
      }
      span.appendChild(contentEl);
      out.appendChild(span);
    });
    document.getElementById("toggle-ln").textContent = "line numbers: " + lnMode;
    var tsBtn = document.getElementById("toggle-ts");
    tsBtn.textContent = hasTimestampMetadata ? "timestamps: " + tsMode : "timestamps: unavailable";
    syncHighlightMode();
  }
  document.getElementById("toggle-ln").addEventListener("click", function() {
    lnMode = lnMode === "on" ? "off" : "on";
    renderOutput();
  });
  document.getElementById("toggle-ts").addEventListener("click", function() {
    if (!hasTimestampMetadata) return;
    tsMode = tsModes[(tsModes.indexOf(tsMode) + 1) % tsModes.length];
    renderOutput();
  });
  var highlightToggle = document.getElementById("toggle-highlights");
  if (highlightToggle) {
    highlightToggle.addEventListener("click", function() {
      highlightMode = highlightMode === "on" ? "off" : "on";
      setCookie("pref_structured_highlights", highlightMode);
      syncHighlightMode();
    });
  }
  (function() {
    var wrap = document.getElementById("perm-save-wrap");
    var btn = document.getElementById("perm-save-btn");
    var menu = wrap ? wrap.querySelector(".save-menu") : null;
    if (!wrap || !btn) return;
    function resetSaveMenuPosition() {
      if (!menu) return;
      menu.style.position = "";
      menu.style.top = "";
      menu.style.left = "";
      menu.style.right = "";
      menu.style.width = "";
      menu.style.maxWidth = "";
    }
    function positionSaveMenu() {
      if (!menu) return;
      if (!window.matchMedia || !window.matchMedia("(max-width: 640px)").matches) {
        resetSaveMenuPosition();
        return;
      }
      if (!wrap.classList.contains("open")) return;
      var margin = 12;
      var viewportWidth = Math.max(0, window.innerWidth || document.documentElement.clientWidth || 0);
      var rect = btn.getBoundingClientRect();
      var menuWidth = Math.min(220, Math.max(0, viewportWidth - margin * 2));
      var maxLeft = Math.max(margin, viewportWidth - menuWidth - margin);
      var left = Math.min(Math.max(rect.left, margin), maxLeft);
      menu.style.position = "fixed";
      menu.style.top = Math.round(rect.bottom - 1) + "px";
      menu.style.left = Math.round(left) + "px";
      menu.style.right = "auto";
      menu.style.width = Math.round(menuWidth) + "px";
      menu.style.maxWidth = "calc(100vw - 24px)";
    }
    function closeSaveMenu() {
      wrap.classList.remove("open");
      resetSaveMenuPosition();
    }
    btn.addEventListener("click", function() {
      wrap.classList.toggle("open");
      if (wrap.classList.contains("open")) positionSaveMenu();
      else resetSaveMenuPosition();
    });
    if (typeof window.addEventListener === "function") {
      window.addEventListener("resize", positionSaveMenu);
      window.addEventListener("scroll", positionSaveMenu, true);
    }
    if (typeof bindOutsideClickCloseFn === "function") {
      bindOutsideClickCloseFn(wrap, {
        triggers: btn,
        isOpen: function() {
          return wrap.classList.contains("open");
        },
        onClose: closeSaveMenu
      });
    }
  })();
  function downloadName(ext) {
    return appName + "-" + exportHtmlUtils.exportTimestamp() + "." + ext;
  }
  function copyTxt() {
    var text = lines.map(function(entry, index) {
      return displayText(entry, index);
    }).join("\n");
    copyTextToClipboardFn(text).then(function() {
      showToastFn("Copied to clipboard");
    }).catch(function() {
    });
  }
  function saveTxt() {
    var text = lines.map(function(entry, index) {
      return displayText(entry, index);
    }).join("\n");
    downloadBlobAsAttachmentFn(new Blob([text], { type: "text/plain" }), downloadName("txt"));
  }
  function saveHtml() {
    var exportModel2 = exportHtmlUtils.buildExportDocumentModel({
      appName,
      title: label,
      label,
      createdText: createdDisplay || created,
      runMeta: permalinkMeta,
      rawLines,
      command,
      includeCommandOutcomeSummary: commandOutcomeSummariesEnabled
    });
    var result = exportHtmlUtils.buildExportLinesHtml(exportModel2.rawLines, {
      getPrefix: function(entry, i) {
        return formatPrefix(i + 1, entry);
      },
      ansiToHtml: function(text) {
        return ansiUp.ansi_to_html(text);
      }
    });
    var linesHtml = result.linesHtml;
    var summaryHtml = result.summaryHtml;
    var prefixWidth = result.prefixWidth;
    exportHtmlUtils.fetchTerminalExportCss().catch(function() {
      return "";
    }).then(function(exportCss) {
      var html = exportHtmlUtils.buildTerminalExportHtml({
        appName: exportModel2.appName,
        title: exportModel2.title,
        metaLine: exportModel2.metaLine,
        runMeta: exportModel2.runMeta,
        linesHtml,
        summaryHtml,
        prefixWidth,
        fontFacesCss,
        exportCss,
        highlights: highlightMode
      });
      downloadBlobAsAttachmentFn(new Blob([html], { type: "text/html" }), downloadName("html"));
    });
  }
  async function savePdf() {
    var existingPdfUtils = window.ExportPdfUtils || (typeof ExportPdfUtils !== "undefined" ? ExportPdfUtils : null);
    if (!existingPdfUtils && typeof window.loadExportPdfUtils !== "function") {
      alert("PDF library not loaded");
      return;
    }
    var pdfUtils;
    var jsPDF;
    try {
      pdfUtils = existingPdfUtils || await window.loadExportPdfUtils();
      jsPDF = typeof window.loadJsPdf === "function" ? await window.loadJsPdf() : await pdfUtils.loadJsPdf();
    } catch (_) {
      alert("PDF library not loaded");
      return;
    }
    var exportModel2 = exportHtmlUtils.buildExportDocumentModel({
      appName,
      title: label,
      label,
      createdText: createdDisplay || created,
      runMeta: permalinkMeta,
      rawLines,
      command,
      includeCommandOutcomeSummary: commandOutcomeSummariesEnabled
    });
    var ansiUpPdf = new AnsiUpCtor();
    ansiUpPdf.use_classes = false;
    var doc = await pdfUtils.buildTerminalExportPdf({
      jsPDF,
      appName: exportModel2.appName,
      metaLine: exportModel2.metaLine,
      runMeta: exportModel2.runMeta,
      rawLines: exportModel2.rawLines,
      getPrefix: function(entry, i) {
        return formatPrefix(i + 1, entry);
      },
      ansiToHtml: function(text) {
        return ansiUpPdf.ansi_to_html(text);
      }
    });
    doc.save(downloadName("pdf"));
  }
  document.addEventListener("click", function(e) {
    var target = e.target.closest("[data-action]");
    if (!target) return;
    var action = target.dataset.action;
    if (action === "copy-txt") copyTxt();
    else if (action === "save-txt") saveTxt();
    else if (action === "save-html") saveHtml();
    else if (action === "save-pdf") void savePdf();
    else return;
    var saveWrap = document.getElementById("perm-save-wrap");
    if (saveWrap) saveWrap.classList.remove("open");
  });
  renderOutput();
})();
