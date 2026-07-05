import {
  apiFetch
} from "./static-chunk-5i2t3zlu.acdd7b56baea.js";
import {
  bindDismissible,
  bindMobileSheet
} from "./static-chunk-4m44pm74.0a8001fa1d52.js";
import {
  enhanceAppSelects,
  refocusComposerAfterAction,
  syncAppSelect
} from "./static-chunk-yo5cjr7d.b86e0c93eff0.js";

// app/static/js/features/findings/finding_triage_editor.js
var DarklabFindingTriageEditor = null;
(function findingTriageEditorModule(global) {
  "use strict";
  const bindDismissible2 = typeof bindDismissible === "function" ? bindDismissible : null;
  const bindMobileSheet2 = typeof bindMobileSheet === "function" ? bindMobileSheet : null;
  const enhanceAppSelects2 = typeof enhanceAppSelects === "function" ? enhanceAppSelects : null;
  const refocusComposerAfterAction2 = typeof refocusComposerAfterAction === "function" ? refocusComposerAfterAction : null;
  const syncAppSelect2 = typeof syncAppSelect === "function" ? syncAppSelect : null;
  const VERIFICATION_STATES = [
    { value: "not_started", label: "Not started" },
    { value: "ready_to_verify", label: "Ready to verify" },
    { value: "verified", label: "Verified" },
    { value: "needs_retest", label: "Needs retest" },
    { value: "not_applicable", label: "Not applicable" }
  ];
  const MAX_TEXT_LENGTH = 2e4;
  let state = {
    finding: null,
    options: {},
    bound: false
  };
  function el(id) {
    return document.getElementById(id);
  }
  function api() {
    return typeof apiFetch === "function" && apiFetch || (typeof global.fetch === "function" ? global.fetch.bind(global) : null);
  }
  function text(value, fallback = "") {
    const normalized = String(value || "").trim();
    return normalized || fallback;
  }
  function titleForFinding(finding) {
    return text(finding && (finding.title || finding.raw_line || finding.id), "Finding");
  }
  function verificationStatusLabel2(value) {
    const normalized = String(value || "not_started");
    const found = VERIFICATION_STATES.find((item) => item.value === normalized);
    return found ? found.label : normalized;
  }
  function verificationStatusTone2(value) {
    const normalized = String(value || "not_started");
    if (normalized === "verified") return "green";
    if (normalized === "needs_retest") return "amber";
    return "muted";
  }
  function compactTriage2(triage) {
    const item = triage && typeof triage === "object" ? triage : {};
    return {
      verification_status: String(item.verification_status || "not_started"),
      has_remediation: !!String(item.remediation || "").trim() || !!item.has_remediation,
      has_verification_steps: !!String(item.verification_steps || "").trim() || !!item.has_verification_steps,
      has_verification_notes: !!String(item.verification_notes || "").trim() || !!item.has_verification_notes,
      remediation_preview: text(item.remediation_preview || item.remediation),
      verification_steps_preview: text(item.verification_steps_preview || item.verification_steps)
    };
  }
  function triageFromForm() {
    return {
      remediation: String(el("finding-triage-remediation")?.value || "").trim(),
      verification_steps: String(el("finding-triage-verification-steps")?.value || "").trim(),
      verification_status: String(el("finding-triage-status")?.value || "not_started"),
      verification_notes: String(el("finding-triage-verification-notes")?.value || "").trim()
    };
  }
  function syncStatusSelect() {
    const statusSelect = el("finding-triage-status");
    if (statusSelect && typeof syncAppSelect2 === "function") syncAppSelect2(statusSelect);
  }
  function setDisabled(disabled) {
    [
      el("finding-triage-remediation"),
      el("finding-triage-verification-steps"),
      el("finding-triage-status"),
      el("finding-triage-verification-notes"),
      el("finding-triage-save")
    ].forEach((node) => {
      if (node) node.disabled = !!disabled;
    });
    syncStatusSelect();
  }
  function setMessage(message = "", { error = false } = {}) {
    const node = el("finding-triage-message");
    if (!node) return;
    node.textContent = message;
    node.classList.toggle("u-hidden", !message);
    node.classList.toggle("is-error", !!error);
  }
  function isOpen() {
    return !!el("finding-triage-overlay")?.classList.contains("open");
  }
  function close() {
    const overlay = el("finding-triage-overlay");
    if (!overlay) return;
    overlay.classList.add("u-hidden");
    overlay.classList.remove("open");
    overlay.setAttribute("aria-hidden", "true");
    state.finding = null;
    state.options = {};
    if (typeof refocusComposerAfterAction2 === "function") {
      refocusComposerAfterAction2({ defer: true });
    }
  }
  async function requestTriage(findingId) {
    const resp = await api()(`/findings/${encodeURIComponent(findingId)}/triage`, { cache: "no-store" });
    if (!resp.ok) {
      const data2 = await resp.json().catch(() => ({}));
      throw new Error(data2 && data2.error ? data2.error : `HTTP ${resp.status}`);
    }
    const data = await resp.json().catch(() => ({}));
    return data && data.triage && typeof data.triage === "object" ? data.triage : {};
  }
  function populate(triage) {
    const status = String(triage && triage.verification_status || "not_started");
    const remediation = el("finding-triage-remediation");
    const steps = el("finding-triage-verification-steps");
    const statusSelect = el("finding-triage-status");
    const notes = el("finding-triage-verification-notes");
    if (remediation) remediation.value = String(triage && triage.remediation || "");
    if (steps) steps.value = String(triage && triage.verification_steps || "");
    if (statusSelect) statusSelect.value = VERIFICATION_STATES.some((item) => item.value === status) ? status : "not_started";
    if (notes) notes.value = String(triage && triage.verification_notes || "");
    syncStatusSelect();
  }
  function validate(payload) {
    for (const field of ["remediation", "verification_steps", "verification_notes"]) {
      if (String(payload[field] || "").length > MAX_TEXT_LENGTH) {
        return `${field.replace(/_/g, " ")} must be ${MAX_TEXT_LENGTH.toLocaleString()} characters or fewer.`;
      }
    }
    return "";
  }
  async function save() {
    const findingId = String(state.finding && state.finding.id || "");
    if (!findingId) return;
    if (state.options && state.options.canEdit === false) {
      setMessage("View-only team members can read these details but cannot save changes.", { error: true });
      return;
    }
    const payload = triageFromForm();
    const validationError = validate(payload);
    if (validationError) {
      setMessage(validationError, { error: true });
      return;
    }
    setMessage("");
    setDisabled(true);
    try {
      const resp = await api()(`/findings/${encodeURIComponent(findingId)}/triage`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data && data.error ? data.error : `HTTP ${resp.status}`);
      const triage = data && data.triage && typeof data.triage === "object" ? data.triage : payload;
      if (state.finding && typeof state.finding === "object") {
        state.finding.triage = compactTriage2(triage);
        state.finding.verification_status = state.finding.triage.verification_status;
      }
      const onSaved = state.options && typeof state.options.onSaved === "function" ? state.options.onSaved : null;
      const savedFinding = state.finding;
      close();
      if (onSaved) await onSaved(triage, savedFinding);
    } catch (err) {
      setMessage(err.message || "Could not save finding triage.", { error: true });
    } finally {
      if (isOpen()) setDisabled(!(state.options && state.options.canEdit !== false));
    }
  }
  function bindOnce() {
    if (state.bound) return;
    state.bound = true;
    el("finding-triage-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      save();
    });
    el("finding-triage-close")?.addEventListener("click", close);
    el("finding-triage-cancel")?.addEventListener("click", close);
    const overlay = el("finding-triage-overlay");
    if (overlay && typeof bindDismissible2 === "function") {
      bindDismissible2(overlay, {
        level: "modal",
        isOpen,
        onClose: close,
        closeButtons: null
      });
    }
    if (overlay && typeof bindMobileSheet2 === "function") {
      bindMobileSheet2(el("finding-triage-modal"), { onClose: close });
    }
  }
  function bindOpenChrome(overlay) {
    if (typeof enhanceAppSelects2 === "function") enhanceAppSelects2(overlay);
  }
  async function open(finding, options = {}) {
    const overlay = el("finding-triage-overlay");
    if (!overlay) throw new Error("Finding triage editor is not available.");
    const findingId = String(finding && finding.id || "");
    if (!findingId) throw new Error("Finding is missing its identifier.");
    bindOnce();
    state.finding = finding;
    state.options = options || {};
    const subtitle = el("finding-triage-subtitle");
    if (subtitle) subtitle.textContent = titleForFinding(finding);
    setMessage("Loading...");
    populate(compactTriage2(finding.triage || { verification_status: finding.verification_status }));
    setDisabled(true);
    overlay.classList.remove("u-hidden");
    overlay.classList.add("open");
    overlay.setAttribute("aria-hidden", "false");
    bindOpenChrome(overlay);
    const canEdit = state.options.canEdit !== false;
    try {
      const triage = await requestTriage(findingId);
      populate(triage);
      setMessage(canEdit ? "" : "View-only team members can read these details but cannot save changes.");
      setDisabled(!canEdit);
      window.setTimeout(() => el("finding-triage-remediation")?.focus({ preventScroll: true }), 0);
    } catch (err) {
      setMessage(err.message || "Could not load finding triage.", { error: true });
      setDisabled(true);
    }
  }
  DarklabFindingTriageEditor = {
    compactTriage: compactTriage2,
    close,
    isOpen,
    open,
    verificationStatusLabel: verificationStatusLabel2,
    verificationStatusTone: verificationStatusTone2,
    verificationStates: VERIFICATION_STATES.slice()
  };
})(typeof window !== "undefined" ? window : globalThis);
var compactTriage = DarklabFindingTriageEditor.compactTriage;
var closeFindingTriageEditor = DarklabFindingTriageEditor.close;
var isFindingTriageEditorOpen = DarklabFindingTriageEditor.isOpen;
var openFindingTriageEditor = DarklabFindingTriageEditor.open;
var verificationStatusLabel = DarklabFindingTriageEditor.verificationStatusLabel;
var verificationStatusTone = DarklabFindingTriageEditor.verificationStatusTone;
var verificationStates = DarklabFindingTriageEditor.verificationStates;

export {
  DarklabFindingTriageEditor,
  verificationStatusLabel,
  verificationStatusTone
};
