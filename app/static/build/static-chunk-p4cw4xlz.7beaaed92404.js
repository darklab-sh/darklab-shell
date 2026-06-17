import {
  _finalizeClientSideCommandStatus,
  _persistClientSideRun,
  _recordSuccessfulLocalCommand,
  _runtimeContextSpec,
  _runtimeHint,
  _runtimePlaceholderHint,
  _setPendingTerminalConfirm,
  _workspaceCommandTokens,
  activateTab,
  appendCommandEcho,
  appendLine,
  cancelWelcome2 as cancelWelcome,
  clearTab,
  closeMajorOverlays,
  hasPendingOutputBatch,
  setStatus,
  setTabStatus,
  setWorkflowHandlers,
  submitComposerCommand2 as submitComposerCommand,
  welcomeOwnsTab,
  wireFaqCommandChips
} from "./static-chunk-rhx4oneb.a213558b0b82.js";
import {
  showToast
} from "./static-chunk-poi5czx6.3f5c94749765.js";
import {
  bindPressable,
  showConfirm
} from "./static-chunk-fik64llj.1291b1f4f79b.js";
import {
  useMobileTerminalViewportMode
} from "./static-chunk-yu6ty7m2.96c3ee208a44.js";
import {
  emitUiEvent,
  getActiveTabId,
  onUiEvent
} from "./static-chunk-sgyzdmxn.7d1842f12a94.js";
import {
  apiFetch,
  hasRuntimeHandler
} from "./static-chunk-i34eiczq.4bb950c346dc.js";

// app/static/js/features/workflows/workflows.js
var WORKFLOWS_GLOBAL = typeof window !== "undefined" ? window : globalThis;
function _workflowGlobalFunction(name) {
  const fn = WORKFLOWS_GLOBAL && WORKFLOWS_GLOBAL[name];
  return typeof fn === "function" ? fn : null;
}
function _workflowActiveTabId() {
  if (typeof getActiveTabId === "function") return getActiveTabId();
  const readActiveTabId = _workflowGlobalFunction("getActiveTabId");
  if (readActiveTabId) return readActiveTabId();
  return WORKFLOWS_GLOBAL?.APP_STATE?.activeTabId || null;
}
function _workflowAppendLine(text, cls = "", tabId = _workflowActiveTabId()) {
  const append = typeof appendLine === "function" && appendLine || _workflowGlobalFunction("appendLine");
  if (append) append(text, cls, tabId);
}
function _workflowBindPressable(el, opts) {
  const bind = typeof bindPressable === "function" && bindPressable || _workflowGlobalFunction("bindPressable");
  return bind ? bind(el, opts) : null;
}
function _workflowCloseMajorOverlays() {
  const close = typeof closeMajorOverlays === "function" && closeMajorOverlays || _workflowGlobalFunction("_closeMajorOverlays");
  if (close) close();
  const workflowOverlay = document.getElementById("workflows-overlay");
  if (workflowOverlay && workflowOverlay.classList.contains("open")) {
    workflowOverlay.classList.remove("open");
    workflowOverlay.classList.add("u-hidden");
    workflowOverlay.setAttribute("aria-hidden", "true");
  }
}
function _workflowWireFaqCommandChips(root) {
  const wire = typeof wireFaqCommandChips === "function" && wireFaqCommandChips || _workflowGlobalFunction("wireFaqCommandChips");
  if (wire) wire(root);
}
function _workflowApiFetch(...args) {
  const fetcher = (typeof hasRuntimeHandler === "function" && hasRuntimeHandler("apiFetch") && typeof apiFetch === "function" ? apiFetch : null) || _workflowGlobalFunction("apiFetch");
  if (!fetcher) throw new Error("apiFetch is unavailable");
  return fetcher(...args);
}
function _workflowRuntimeHint(value, description = "", insertValue = null) {
  const hint = typeof _runtimeHint === "function" && _runtimeHint || _workflowGlobalFunction("_runtimeHint");
  return hint ? hint(value, description, insertValue) : { value, description, ...insertValue != null ? { insertValue } : {} };
}
function _workflowRuntimePlaceholderHint(value, description = "") {
  const hint = typeof _runtimePlaceholderHint === "function" && _runtimePlaceholderHint || _workflowGlobalFunction("_runtimePlaceholderHint");
  if (hint) return hint(value, description);
  return { value, description, hintOnly: true };
}
function _workflowRuntimeContextSpec(spec = {}) {
  const contextSpec = typeof _runtimeContextSpec === "function" && _runtimeContextSpec || _workflowGlobalFunction("_runtimeContextSpec");
  return contextSpec ? contextSpec(spec) : spec;
}
var WORKFLOW_TOKEN_RE = /{{\s*([a-z][a-z0-9_]*)\s*}}/g;
var WORKFLOW_INPUT_STATE_KEY = "workflow_input_state_v1";
var _workflowRunQueueByTab = /* @__PURE__ */ new Map();
var workflowCatalogItems = typeof globalThis !== "undefined" && Array.isArray(globalThis.__workflowCatalogItems) ? globalThis.__workflowCatalogItems.slice() : [];
var workflowCatalogLoadPromise = null;
var _workflowEditorWorkflow = null;
function getWorkflowStorageKey(workflow) {
  const id = String(workflow?.id || "").trim();
  if (id) return id;
  const title = String(workflow?.title || "").trim();
  const description = String(workflow?.description || "").trim();
  return `${title}::${description}`;
}
function workflowSlug(value) {
  return String(value || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "workflow";
}
function workflowLookupKeys(workflow) {
  const keys = [];
  const id = String(workflow?.id || "").trim();
  const title = String(workflow?.title || "").trim();
  [id, title, workflowSlug(title)].forEach((key) => {
    const value = String(key || "").trim().toLowerCase();
    if (value && !keys.includes(value)) keys.push(value);
  });
  return keys;
}
function workflowCliName(workflow) {
  const id = String(workflow?.id || "").trim();
  return workflowSlug(workflow?.title || id || "workflow");
}
function readWorkflowInputState() {
  if (typeof localStorage === "undefined") return {};
  try {
    const raw = localStorage.getItem(WORKFLOW_INPUT_STATE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (_err) {
    return {};
  }
}
function writeWorkflowInputState(nextState) {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(WORKFLOW_INPUT_STATE_KEY, JSON.stringify(nextState || {}));
  } catch (_err) {
  }
}
function loadWorkflowInputValues(workflow) {
  const base = getWorkflowInputValues(workflow);
  const state = readWorkflowInputState();
  const saved = state[getWorkflowStorageKey(workflow)];
  if (!saved || typeof saved !== "object") return base;
  const next = { ...base };
  Object.entries(saved).forEach(([key, value]) => {
    const input = (workflow?.inputs || []).find((item) => item.id === key);
    if (!input) return;
    next[key] = sanitizeWorkflowInputValue(input, value);
  });
  return next;
}
function persistWorkflowInputValues(workflow, values) {
  const state = readWorkflowInputState();
  const nextState = { ...state };
  nextState[getWorkflowStorageKey(workflow)] = { ...values || {} };
  writeWorkflowInputState(nextState);
}
function sanitizeWorkflowInputValue(input, value) {
  const raw = String(value == null ? "" : value).trim();
  if (!input || !raw) return raw;
  if (input.type === "port") return raw.replace(/[^\d]/g, "");
  return raw;
}
function getWorkflowInputValues(workflow) {
  const values = {};
  const inputs = Array.isArray(workflow?.inputs) ? workflow.inputs : [];
  inputs.forEach((input) => {
    values[input.id] = sanitizeWorkflowInputValue(input, input.default || "");
  });
  return values;
}
function renderWorkflowCommandTemplate(template, values) {
  return String(template || "").replace(WORKFLOW_TOKEN_RE, (_match, token) => values[token] || "");
}
function workflowInputsReady(workflow, values) {
  const inputs = Array.isArray(workflow?.inputs) ? workflow.inputs : [];
  return inputs.every((input) => !input.required || String(values[input.id] || "").trim().length > 0);
}
function buildRenderedWorkflow(workflow, values) {
  const renderedValues = { ...values || {} };
  const ready = workflowInputsReady(workflow, renderedValues);
  const steps = Array.isArray(workflow?.steps) ? workflow.steps : [];
  return {
    ready,
    steps: steps.map((step) => ({
      ...step,
      renderedCmd: renderWorkflowCommandTemplate(step.cmd || "", renderedValues).trim()
    }))
  };
}
function workflowInputTypeFromName(name) {
  const value = String(name || "").toLowerCase();
  if (value.includes("url")) return "url";
  if (value.includes("port")) return "port";
  if (value.includes("path") || value.includes("file") || value.includes("wordlist")) return "path";
  if (value.includes("domain")) return "domain";
  return "host";
}
function workflowInputLabel(inputId) {
  return String(inputId || "").replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}
function collectWorkflowTokensFromSteps(steps) {
  const seen = [];
  (Array.isArray(steps) ? steps : []).forEach((step) => {
    [step?.cmd, step?.note].forEach((value) => {
      const text = String(value || "");
      let match = WORKFLOW_TOKEN_RE.exec(text);
      while (match) {
        const token = String(match[1] || "").trim();
        if (token && !seen.includes(token)) seen.push(token);
        match = WORKFLOW_TOKEN_RE.exec(text);
      }
      WORKFLOW_TOKEN_RE.lastIndex = 0;
    });
  });
  return seen;
}
function inferWorkflowInputsFromSteps(steps) {
  return collectWorkflowTokensFromSteps(steps).map((id) => ({
    id,
    label: workflowInputLabel(id),
    type: workflowInputTypeFromName(id),
    required: true,
    placeholder: id,
    default: "",
    help: ""
  }));
}
function runWorkflowCommands(commands) {
  const runnable = (commands || []).map((cmd) => String(cmd || "").trim()).filter(Boolean);
  if (!runnable.length) return;
  const targetTabId = _workflowActiveTabId();
  if (!targetTabId) return;
  const welcomeOwnsTab2 = typeof welcomeOwnsTab === "function" && welcomeOwnsTab || _workflowGlobalFunction("welcomeOwnsTab");
  if (typeof welcomeOwnsTab2 === "function" && welcomeOwnsTab2(targetTabId)) {
    const cancelWelcome2 = typeof cancelWelcome === "function" && cancelWelcome || _workflowGlobalFunction("cancelWelcome");
    const clearTab2 = typeof clearTab === "function" && clearTab || _workflowGlobalFunction("clearTab");
    const setTabStatus2 = typeof setTabStatus === "function" && setTabStatus || _workflowGlobalFunction("setTabStatus");
    if (cancelWelcome2) cancelWelcome2(targetTabId);
    if (clearTab2) clearTab2(targetTabId);
    if (setTabStatus2) setTabStatus2(targetTabId, "idle");
  }
  _workflowCloseMajorOverlays();
  _workflowRunQueueByTab.set(targetTabId, {
    commands: runnable.slice(),
    nextIndex: 1,
    total: runnable.length
  });
  const activateTab2 = typeof activateTab === "function" && activateTab || _workflowGlobalFunction("activateTab");
  if (activateTab2) activateTab2(targetTabId);
  if (runnable.length > 1) {
    _workflowAppendLine(`[workflow] Running ${runnable.length} steps sequentially in this tab.`, "notice", targetTabId);
  }
  const submitComposerCommand2 = typeof submitComposerCommand === "function" && submitComposerCommand || _workflowGlobalFunction("submitComposerCommand");
  if (submitComposerCommand2) {
    submitComposerCommand2(runnable[0], {
      dismissKeyboard: true,
      focusAfterSubmit: true
    });
  }
}
function _runNextWorkflowQueueStep(tabId) {
  const queue = _workflowRunQueueByTab.get(tabId);
  if (!queue) return;
  const nextCommand = queue.commands[queue.nextIndex];
  if (!nextCommand) {
    _workflowRunQueueByTab.delete(tabId);
    _workflowAppendLine("[workflow] Completed all queued steps.", "exit-ok", tabId);
    return;
  }
  queue.nextIndex += 1;
  _workflowAppendLine(`[workflow] Continuing with step ${queue.nextIndex}/${queue.total}.`, "notice", tabId);
  const activateTab2 = typeof activateTab === "function" && activateTab || _workflowGlobalFunction("activateTab");
  if (activateTab2) activateTab2(tabId, { focusComposer: false });
  const submitComposerCommand2 = typeof submitComposerCommand === "function" && submitComposerCommand || _workflowGlobalFunction("submitComposerCommand");
  if (submitComposerCommand2) {
    submitComposerCommand2(nextCommand, {
      dismissKeyboard: false,
      focusAfterSubmit: false
    });
  }
}
function _scheduleNextWorkflowQueueStep(tabId) {
  const waitForFlush = () => {
    if (!_workflowRunQueueByTab.has(tabId)) return;
    const hasPendingOutputBatch2 = typeof hasPendingOutputBatch === "function" && hasPendingOutputBatch || _workflowGlobalFunction("hasPendingOutputBatch");
    if (hasPendingOutputBatch2 && hasPendingOutputBatch2(tabId)) {
      setTimeout(waitForFlush, 20);
      return;
    }
    _runNextWorkflowQueueStep(tabId);
  };
  setTimeout(waitForFlush, 0);
}
var workflowOnUiEvent = typeof onUiEvent === "function" && onUiEvent || _workflowGlobalFunction("onUiEvent");
if (typeof workflowOnUiEvent === "function") {
  workflowOnUiEvent("app:tab-status-changed", (e) => {
    const tabId = e?.detail?.id;
    const status = e?.detail?.status;
    if (!tabId || !_workflowRunQueueByTab.has(tabId) || status === "running") return;
    if (status === "killed") {
      _workflowRunQueueByTab.delete(tabId);
      _workflowAppendLine("[workflow] Queue stopped because the current step was killed.", "denied", tabId);
      return;
    }
    _scheduleNextWorkflowQueueStep(tabId);
  });
}
function renderWorkflowInputCard(card, workflow) {
  const inputs = Array.isArray(workflow?.inputs) ? workflow.inputs : [];
  if (!inputs.length) return null;
  const panel = document.createElement("div");
  panel.className = "workflow-input-panel";
  const intro = document.createElement("div");
  intro.className = "workflow-input-intro";
  intro.textContent = "Fill in your target to preview the exact commands before loading or running a step.";
  panel.appendChild(intro);
  const grid = document.createElement("div");
  grid.className = "workflow-input-grid";
  panel.appendChild(grid);
  const values = loadWorkflowInputValues(workflow);
  const hint = document.createElement("div");
  hint.className = "workflow-input-hint";
  const actions = document.createElement("div");
  actions.className = "workflow-input-actions";
  const runAllBtn = document.createElement("button");
  runAllBtn.type = "button";
  runAllBtn.className = "btn btn-secondary btn-compact workflow-run-all";
  runAllBtn.textContent = "Run all";
  runAllBtn.title = "Run each rendered workflow step sequentially in this tab";
  actions.appendChild(runAllBtn);
  panel.appendChild(actions);
  inputs.forEach((input) => {
    const field = document.createElement("label");
    field.className = "workflow-input-field";
    const label = document.createElement("span");
    label.className = "workflow-input-label";
    label.textContent = input.label || input.id || "";
    field.appendChild(label);
    const control = document.createElement("input");
    control.className = "options-token-input workflow-input-control";
    control.type = input.type === "port" ? "text" : "text";
    control.autocomplete = "off";
    control.autocapitalize = "none";
    control.autocorrect = "off";
    control.spellcheck = false;
    control.inputMode = input.type === "port" ? "numeric" : "text";
    control.placeholder = input.placeholder || "";
    control.value = values[input.id] || "";
    control.dataset.workflowInputId = input.id;
    if (input.required) {
      control.required = true;
      control.setAttribute("aria-required", "true");
    }
    field.appendChild(control);
    if (input.help) {
      const help = document.createElement("span");
      help.className = "workflow-input-help";
      help.textContent = input.help;
      field.appendChild(help);
    }
    grid.appendChild(field);
  });
  panel.appendChild(hint);
  const applyRenderedState = () => {
    const rendered = buildRenderedWorkflow(workflow, values);
    const stepsEl = card.querySelector(".workflow-steps");
    if (!stepsEl) return;
    stepsEl.querySelectorAll(".workflow-step").forEach((stepEl, idx) => {
      const chip = stepEl.querySelector(".workflow-step-cmd");
      const runBtn = stepEl.querySelector(".workflow-step-run");
      const renderedStep = rendered.steps[idx];
      const renderedCmd = renderedStep?.renderedCmd || "";
      if (chip) {
        chip.textContent = rendered.ready ? renderedCmd || renderedStep?.cmd || "" : renderedStep?.cmd || "";
        if (rendered.ready && renderedCmd) {
          chip.title = "Click to load into prompt";
          chip.dataset.faqCommand = renderedCmd;
          chip.classList.remove("is-disabled");
        } else {
          chip.title = "Fill required workflow inputs to load this step";
          delete chip.dataset.faqCommand;
          chip.classList.add("is-disabled");
        }
      }
      if (runBtn) {
        runBtn.dataset.workflowStepCmd = rendered.ready ? renderedCmd : "";
        runBtn.disabled = !(rendered.ready && renderedCmd);
        runBtn.setAttribute("aria-disabled", runBtn.disabled ? "true" : "false");
        runBtn.title = runBtn.disabled ? "Fill required workflow inputs to run this step" : "Run this step";
        runBtn.setAttribute("aria-label", rendered.ready && renderedCmd ? `Run: ${renderedCmd}` : "Run this step");
      }
    });
    runAllBtn.disabled = !(rendered.ready && rendered.steps.some((step) => step.renderedCmd));
    runAllBtn.setAttribute("aria-disabled", runAllBtn.disabled ? "true" : "false");
    hint.textContent = rendered.ready ? "Rendered commands are live. Click a chip to load it, use ▶ to run one step, or Run all to execute the full workflow here in sequence." : "Fill the required fields to render runnable commands.";
    _workflowWireFaqCommandChips(card);
    wireWorkflowStepRunButtons(card);
  };
  _workflowBindPressable(runAllBtn, {
    onActivate: () => {
      const rendered = buildRenderedWorkflow(workflow, values);
      if (!rendered.ready) return;
      runWorkflowCommands(rendered.steps.map((step) => step.renderedCmd));
    }
  });
  grid.querySelectorAll(".workflow-input-control").forEach((control) => {
    control.addEventListener("input", () => {
      const input = inputs.find((item) => item.id === control.dataset.workflowInputId);
      values[control.dataset.workflowInputId || ""] = sanitizeWorkflowInputValue(input, control.value);
      if (input?.type === "port" && control.value !== values[control.dataset.workflowInputId || ""]) {
        control.value = values[control.dataset.workflowInputId || ""];
      }
      persistWorkflowInputValues(workflow, values);
      applyRenderedState();
    });
  });
  panel._workflowApplyRenderedState = applyRenderedState;
  return panel;
}
function workflowEditorRefs() {
  return {
    overlay: document.getElementById("workflow-editor-overlay"),
    form: document.getElementById("workflow-editor-form"),
    title: document.getElementById("workflow-editor-title"),
    titleInput: document.getElementById("workflow-editor-title-input"),
    descriptionInput: document.getElementById("workflow-editor-description-input"),
    steps: document.getElementById("workflow-editor-steps"),
    msg: document.getElementById("workflow-editor-msg"),
    saveBtn: document.getElementById("workflow-editor-save-btn")
  };
}
function setWorkflowEditorMessage(message = "", isError = false) {
  const { msg } = workflowEditorRefs();
  if (!msg) return;
  msg.textContent = message;
  msg.classList.toggle("is-error", !!isError);
}
function createWorkflowEditorStep(step = {}, index = 0) {
  const row = document.createElement("div");
  row.className = "workflow-editor-step";
  row.dataset.workflowEditorStep = "1";
  const header = document.createElement("div");
  header.className = "workflow-editor-step-header";
  const title = document.createElement("span");
  title.className = "workflow-editor-step-title";
  title.textContent = `Step ${index + 1}`;
  header.appendChild(title);
  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "btn btn-ghost btn-icon-only btn-compact workflow-editor-remove-step";
  removeBtn.textContent = "×";
  removeBtn.title = "Remove step";
  removeBtn.setAttribute("aria-label", "Remove workflow step");
  header.appendChild(removeBtn);
  row.appendChild(header);
  const cmdLabel = document.createElement("label");
  cmdLabel.className = "workflow-editor-field";
  const cmdText = document.createElement("span");
  cmdText.className = "workflow-input-label";
  cmdText.textContent = "Command";
  const cmdInput = document.createElement("input");
  cmdInput.className = "options-token-input workflow-editor-step-command";
  cmdInput.type = "text";
  cmdInput.autocomplete = "off";
  cmdInput.autocapitalize = "none";
  cmdInput.autocorrect = "off";
  cmdInput.spellcheck = false;
  cmdInput.inputMode = "text";
  cmdInput.value = step.cmd || "";
  cmdInput.placeholder = "nmap -F {{host}}";
  cmdLabel.append(cmdText, cmdInput);
  row.appendChild(cmdLabel);
  const noteLabel = document.createElement("label");
  noteLabel.className = "workflow-editor-field";
  const noteText = document.createElement("span");
  noteText.className = "workflow-input-label";
  noteText.textContent = "Note";
  const noteInput = document.createElement("input");
  noteInput.className = "options-token-input workflow-editor-step-note";
  noteInput.type = "text";
  noteInput.autocomplete = "off";
  noteInput.autocapitalize = "none";
  noteInput.autocorrect = "off";
  noteInput.spellcheck = false;
  noteInput.inputMode = "text";
  noteInput.value = step.note || "";
  noteInput.placeholder = "Optional context for this step";
  noteLabel.append(noteText, noteInput);
  row.appendChild(noteLabel);
  removeBtn.addEventListener("click", () => {
    row.remove();
    refreshWorkflowEditorStepNumbers();
  });
  return row;
}
function refreshWorkflowEditorStepNumbers() {
  const { steps } = workflowEditorRefs();
  if (!steps) return;
  const rows = [...steps.querySelectorAll("[data-workflow-editor-step]")];
  rows.forEach((row, index) => {
    const title = row.querySelector(".workflow-editor-step-title");
    if (title) title.textContent = `Step ${index + 1}`;
    const removeBtn = row.querySelector(".workflow-editor-remove-step");
    if (removeBtn) removeBtn.disabled = rows.length <= 1;
  });
}
function addWorkflowEditorStep(step = {}) {
  const { steps } = workflowEditorRefs();
  if (!steps) return;
  const row = createWorkflowEditorStep(step, steps.querySelectorAll("[data-workflow-editor-step]").length);
  steps.appendChild(row);
  refreshWorkflowEditorStepNumbers();
}
function workflowPayloadFromEditor() {
  const { titleInput, descriptionInput, steps } = workflowEditorRefs();
  const rawSteps = [...steps?.querySelectorAll("[data-workflow-editor-step]") || []].map((row) => ({
    cmd: String(row.querySelector(".workflow-editor-step-command")?.value || "").trim(),
    note: String(row.querySelector(".workflow-editor-step-note")?.value || "").trim()
  })).filter((step) => step.cmd);
  return {
    title: String(titleInput?.value || "").trim(),
    description: String(descriptionInput?.value || "").trim(),
    inputs: inferWorkflowInputsFromSteps(rawSteps),
    steps: rawSteps
  };
}
function openWorkflowEditor(workflow = null) {
  const refs = workflowEditorRefs();
  if (!refs.overlay || !refs.form || !refs.steps) return;
  _workflowEditorWorkflow = workflow && workflow.source === "user" ? workflow : null;
  refs.title.textContent = _workflowEditorWorkflow ? "EDIT WORKFLOW" : "NEW WORKFLOW";
  refs.saveBtn.textContent = _workflowEditorWorkflow ? "Save changes" : "Save workflow";
  refs.titleInput.value = _workflowEditorWorkflow?.title || "";
  refs.descriptionInput.value = _workflowEditorWorkflow?.description || "";
  refs.steps.innerHTML = "";
  const sourceSteps = Array.isArray(_workflowEditorWorkflow?.steps) && _workflowEditorWorkflow.steps.length ? _workflowEditorWorkflow.steps : [{ cmd: "", note: "" }];
  sourceSteps.forEach((step) => addWorkflowEditorStep(step));
  setWorkflowEditorMessage("");
  refs.overlay.classList.remove("u-hidden");
  refs.overlay.classList.add("open");
  refs.overlay.setAttribute("aria-hidden", "false");
  setTimeout(() => {
    const active = document.activeElement;
    const activeIsEditable = active instanceof HTMLInputElement || active instanceof HTMLTextAreaElement || active instanceof HTMLSelectElement || active?.isContentEditable;
    if (activeIsEditable && refs.overlay.contains(active)) return;
    refs.titleInput?.focus();
  }, 0);
}
function closeWorkflowEditor() {
  const { overlay, form } = workflowEditorRefs();
  if (!overlay) return;
  overlay.classList.remove("open");
  overlay.classList.add("u-hidden");
  overlay.setAttribute("aria-hidden", "true");
  if (form) form.reset();
  _workflowEditorWorkflow = null;
}
async function saveWorkflowEditor() {
  const refs = workflowEditorRefs();
  if (!refs.saveBtn) return;
  const payload = workflowPayloadFromEditor();
  if (!payload.title) {
    setWorkflowEditorMessage("Workflow name is required.", true);
    return;
  }
  if (!payload.steps.length) {
    setWorkflowEditorMessage("Add at least one command step.", true);
    return;
  }
  refs.saveBtn.disabled = true;
  setWorkflowEditorMessage("Saving workflow...");
  try {
    const editing = _workflowEditorWorkflow && _workflowEditorWorkflow.id;
    const url = editing ? `/session/workflows/${encodeURIComponent(_workflowEditorWorkflow.id)}` : "/session/workflows";
    const resp = await _workflowApiFetch(url, {
      method: editing ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
    closeWorkflowEditor();
    await reloadWorkflowCatalog();
    const showToast2 = typeof showToast === "function" && showToast || _workflowGlobalFunction("showToast");
    if (showToast2) showToast2(editing ? "Workflow updated" : "Workflow saved");
  } catch (err) {
    setWorkflowEditorMessage(err.message || "Failed to save workflow.", true);
  } finally {
    refs.saveBtn.disabled = false;
  }
}
async function deleteUserWorkflow(workflow) {
  if (!workflow || workflow.source !== "user" || !workflow.id) return;
  let confirmed = true;
  const showConfirm2 = typeof showConfirm === "function" && showConfirm || _workflowGlobalFunction("showConfirm");
  if (showConfirm2) {
    const choice = await showConfirm2({
      body: `Delete workflow "${workflow.title}"?`,
      tone: "danger",
      actions: [
        { id: "cancel", label: "Cancel", role: "cancel" },
        { id: "delete", label: "Delete", role: "destructive" }
      ]
    });
    confirmed = choice === "delete";
  }
  if (!confirmed) return;
  try {
    const resp = await _workflowApiFetch(`/session/workflows/${encodeURIComponent(workflow.id)}`, { method: "DELETE" });
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.error || `HTTP ${resp.status}`);
    }
    await reloadWorkflowCatalog();
    const showToast2 = typeof showToast === "function" && showToast || _workflowGlobalFunction("showToast");
    if (showToast2) showToast2("Workflow deleted");
  } catch (err) {
    const showToast2 = typeof showToast === "function" && showToast || _workflowGlobalFunction("showToast");
    if (showToast2) showToast2(err.message || "Failed to delete workflow", "error");
  }
}
function isMobileWorkflowSheetMode() {
  const useMobile = typeof useMobileTerminalViewportMode === "function" && useMobileTerminalViewportMode || _workflowGlobalFunction("useMobileTerminalViewportMode");
  return !!(useMobile && useMobile());
}
function renderWorkflowItems(items, { emitCatalogEvent = true } = {}) {
  const list = Array.isArray(items) ? items : [];
  const workflowsOverlay = document.getElementById("workflows-overlay");
  if (workflowsOverlay?.dataset?.workflowScoped === "1" && workflowsOverlay.classList.contains("open") && list.length > 1) {
    return;
  }
  workflowCatalogItems = list.slice();
  if (typeof globalThis !== "undefined") globalThis.__workflowCatalogItems = list.slice();
  const body = document.querySelector(".workflows-body");
  if (!body) return;
  body.innerHTML = "";
  const collapseCards = isMobileWorkflowSheetMode();
  let lastSection = null;
  list.forEach((item, idx) => {
    const section = item.source === "user" ? "My workflows" : "Built-ins";
    if (section !== lastSection) {
      const label = document.createElement("div");
      label.className = "workflow-section-label";
      label.textContent = section;
      body.appendChild(label);
      lastSection = section;
    }
    const card = document.createElement("div");
    card.className = "workflow-card workflow-card-accordion";
    if (item.id) card.dataset.workflowId = String(item.id);
    if (item.source === "user") card.classList.add("is-user-workflow");
    if (collapseCards) card.classList.add("is-collapsed");
    const cardBodyId = `workflow-card-body-${idx}`;
    const toggleBtn = document.createElement("button");
    toggleBtn.type = "button";
    toggleBtn.className = "workflow-card-toggle";
    toggleBtn.setAttribute("aria-expanded", collapseCards ? "false" : "true");
    toggleBtn.setAttribute("aria-controls", cardBodyId);
    const heading = document.createElement("span");
    heading.className = "workflow-card-heading";
    const titleEl = document.createElement("span");
    titleEl.className = "workflow-title";
    titleEl.textContent = item.title || "";
    heading.appendChild(titleEl);
    if (item.source === "user") {
      const badge = document.createElement("span");
      badge.className = "workflow-source-badge";
      badge.textContent = "user";
      heading.appendChild(badge);
    }
    toggleBtn.appendChild(heading);
    const toggleIcon = document.createElement("span");
    toggleIcon.className = "workflow-card-toggle-icon";
    toggleIcon.setAttribute("aria-hidden", "true");
    toggleIcon.textContent = "⌄";
    toggleBtn.appendChild(toggleIcon);
    toggleBtn.addEventListener("click", () => {
      const nextExpanded = card.classList.toggle("is-collapsed") === false;
      toggleBtn.setAttribute("aria-expanded", nextExpanded ? "true" : "false");
    });
    card.appendChild(toggleBtn);
    const cardBody = document.createElement("div");
    cardBody.className = "workflow-card-body";
    cardBody.id = cardBodyId;
    if (item.source === "user") {
      const actions = document.createElement("div");
      actions.className = "workflow-card-actions";
      const editBtn = document.createElement("button");
      editBtn.type = "button";
      editBtn.className = "btn btn-secondary btn-compact workflow-edit-btn";
      editBtn.textContent = "Edit";
      editBtn.addEventListener("click", () => openWorkflowEditor(item));
      actions.appendChild(editBtn);
      const deleteBtn = document.createElement("button");
      deleteBtn.type = "button";
      deleteBtn.className = "btn btn-ghost btn-compact workflow-delete-btn";
      deleteBtn.textContent = "Delete";
      deleteBtn.addEventListener("click", () => deleteUserWorkflow(item));
      actions.appendChild(deleteBtn);
      cardBody.appendChild(actions);
    }
    if (item.description) {
      const desc = document.createElement("div");
      desc.className = "workflow-desc";
      desc.textContent = item.description;
      cardBody.appendChild(desc);
    }
    const inputPanel = renderWorkflowInputCard(card, item);
    if (inputPanel) cardBody.appendChild(inputPanel);
    const steps = item.steps || [];
    if (steps.length) {
      const stepsEl = document.createElement("ol");
      stepsEl.className = "workflow-steps";
      steps.forEach((step) => {
        const li = document.createElement("li");
        li.className = "workflow-step";
        const main = document.createElement("div");
        main.className = "workflow-step-main";
        const chip = document.createElement("span");
        chip.className = "allowed-chip faq-chip workflow-step-cmd chip chip-action";
        chip.textContent = step.cmd || "";
        if (inputPanel) {
          chip.title = "Fill required workflow inputs to load this step";
          chip.classList.add("is-disabled");
        } else {
          chip.title = "Click to load into prompt";
          chip.dataset.faqCommand = step.cmd || "";
        }
        main.appendChild(chip);
        const runBtn = document.createElement("button");
        runBtn.type = "button";
        runBtn.className = "btn btn-ghost btn-compact btn-icon-only workflow-step-run";
        runBtn.textContent = "▶";
        if (inputPanel) {
          runBtn.title = "Fill required workflow inputs to run this step";
          runBtn.setAttribute("aria-label", "Run this step");
          runBtn.dataset.workflowStepCmd = "";
          runBtn.disabled = true;
          runBtn.setAttribute("aria-disabled", "true");
        } else {
          runBtn.title = "Run this step";
          runBtn.setAttribute("aria-label", `Run: ${step.cmd || ""}`);
          runBtn.dataset.workflowStepCmd = step.cmd || "";
        }
        main.appendChild(runBtn);
        li.appendChild(main);
        if (step.note) {
          const note = document.createElement("span");
          note.className = "workflow-step-note";
          note.textContent = step.note;
          li.appendChild(note);
        }
        stepsEl.appendChild(li);
      });
      cardBody.appendChild(stepsEl);
    }
    card.appendChild(cardBody);
    if (inputPanel && typeof inputPanel._workflowApplyRenderedState === "function") {
      inputPanel._workflowApplyRenderedState();
    }
    body.appendChild(card);
  });
  _workflowWireFaqCommandChips(body);
  wireWorkflowStepRunButtons(body);
  const emitUiEvent2 = typeof emitUiEvent === "function" && emitUiEvent || _workflowGlobalFunction("emitUiEvent");
  if (emitCatalogEvent && emitUiEvent2) {
    emitUiEvent2("app:workflows-rendered", {
      items: list.slice()
    });
  }
}
async function reloadWorkflowCatalog() {
  const request = (async () => {
    const resp = await _workflowApiFetch("/workflows");
    if (resp && resp.ok === false) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    renderWorkflowItems(data.items || []);
    return data.items || [];
  })();
  workflowCatalogLoadPromise = request;
  try {
    return await request;
  } finally {
    if (workflowCatalogLoadPromise === request) workflowCatalogLoadPromise = null;
  }
}
function ensureWorkflowCatalogLoaded() {
  if (workflowCatalogItems.length) return Promise.resolve(workflowCatalogItems);
  return workflowCatalogLoadPromise || reloadWorkflowCatalog();
}
function activateWorkflowStepRun(cmd) {
  if (!cmd) return;
  _workflowCloseMajorOverlays();
  const submitComposerCommand2 = typeof submitComposerCommand === "function" && submitComposerCommand || _workflowGlobalFunction("submitComposerCommand");
  if (submitComposerCommand2) {
    submitComposerCommand2(cmd, { dismissKeyboard: true });
  }
}
function wireWorkflowStepRunButtons(root) {
  if (!root) return;
  root.querySelectorAll(".workflow-step-run[data-workflow-step-cmd]").forEach((btn) => {
    _workflowBindPressable(btn, {
      onActivate: () => activateWorkflowStepRun(btn.dataset.workflowStepCmd || "")
    });
  });
}
function _workflowCommandTokens(cmd) {
  const workspaceCommandTokens = typeof _workspaceCommandTokens === "function" && _workspaceCommandTokens || _workflowGlobalFunction("_workspaceCommandTokens");
  if (workspaceCommandTokens) return workspaceCommandTokens(cmd);
  const tokens = [];
  const re = /"[^"]*"|'[^']*'|\S+/g;
  let match = re.exec(String(cmd || "").trim());
  while (match) {
    let token = match[0];
    if (token.length >= 2 && (token[0] === '"' && token[token.length - 1] === '"' || token[0] === "'" && token[token.length - 1] === "'")) {
      token = token.slice(1, -1);
    }
    tokens.push(token);
    match = re.exec(String(cmd || "").trim());
  }
  return tokens;
}
function _workflowCliAppend(text, cls = "", tabId = _workflowActiveTabId()) {
  _workflowAppendLine(text, cls, tabId);
}
function _workflowCliSetStatus(status) {
  const setStatus2 = typeof setStatus === "function" && setStatus || _workflowGlobalFunction("setStatus");
  if (setStatus2) setStatus2(status);
}
function _workflowCliRecord(cmd) {
  const record = typeof _recordSuccessfulLocalCommand === "function" && _recordSuccessfulLocalCommand || _workflowGlobalFunction("_recordSuccessfulLocalCommand");
  if (record) record(cmd);
}
function _workflowCliPersist(cmd, lines, status = "ok") {
  const persist = typeof _persistClientSideRun === "function" && _persistClientSideRun || _workflowGlobalFunction("_persistClientSideRun");
  if (persist) persist(cmd, lines, status);
}
function _workflowCliFinish(cmd, lines, status = "ok", tabId = _workflowActiveTabId(), { record = false } = {}) {
  if (record && status !== "fail") _workflowCliRecord(cmd);
  _workflowCliPersist(cmd, lines, status);
  const finalize = typeof _finalizeClientSideCommandStatus === "function" && _finalizeClientSideCommandStatus || _workflowGlobalFunction("_finalizeClientSideCommandStatus");
  if (finalize) {
    finalize(tabId, status);
  } else {
    _workflowCliSetStatus(status);
  }
}
function _workflowFind(selector) {
  const query = String(selector || "").trim().toLowerCase();
  if (!query) return { workflow: null, error: "workflow name is required" };
  const items = workflowCatalogItems || [];
  const exactMatches = items.filter((item) => workflowLookupKeys(item).some((key) => key === query));
  if (exactMatches.length === 1) return { workflow: exactMatches[0], error: "" };
  if (exactMatches.length > 1) {
    return {
      workflow: null,
      error: `ambiguous workflow '${selector}': ${exactMatches.slice(0, 5).map(workflowCliName).join(", ")}`
    };
  }
  const matches = items.filter((item) => workflowLookupKeys(item).some((key) => key.includes(query)));
  if (matches.length === 1) return { workflow: matches[0], error: "" };
  if (matches.length > 1) {
    return {
      workflow: null,
      error: `ambiguous workflow '${selector}': ${matches.slice(0, 5).map(workflowCliName).join(", ")}`
    };
  }
  return { workflow: null, error: `workflow not found: ${selector}` };
}
function _workflowCliUsageLines() {
  return [
    "Usage: workflow [list | show <name> | run <name> [--input value ...]]",
    "Examples:",
    "  workflow list",
    "  workflow show dns-troubleshooting",
    "  workflow run dns-troubleshooting --domain darklab.sh"
  ];
}
function _workflowParseRunArgs(args) {
  const selectors = [];
  const values = {};
  const errors = [];
  for (let index = 0; index < args.length; index += 1) {
    const token = String(args[index] || "");
    if (token.startsWith("--")) {
      const eq = token.indexOf("=");
      const rawName = eq >= 0 ? token.slice(2, eq) : token.slice(2);
      const name = rawName.replace(/-/g, "_").toLowerCase();
      if (!name) {
        errors.push(`invalid flag '${token}'`);
        continue;
      }
      let value = eq >= 0 ? token.slice(eq + 1) : "";
      if (eq < 0) {
        index += 1;
        value = args[index] || "";
      }
      if (!String(value || "").trim()) errors.push(`missing value for --${rawName}`);
      values[name] = value;
    } else {
      selectors.push(token);
    }
  }
  return { selector: selectors.join(" "), values, errors };
}
function _workflowResolvedValues(workflow, provided = {}) {
  const values = getWorkflowInputValues(workflow);
  Object.entries(provided || {}).forEach(([key, value]) => {
    const input = (workflow.inputs || []).find((item) => item.id === key);
    if (!input) return;
    values[key] = sanitizeWorkflowInputValue(input, value);
  });
  return values;
}
function _workflowMissingInputs(workflow, values) {
  return (workflow.inputs || []).filter((input) => input.required && !String(values[input.id] || "").trim());
}
function _workflowRunResolved(workflow, values, tabId) {
  const rendered = buildRenderedWorkflow(workflow, values);
  if (!rendered.ready) {
    _workflowCliAppend("[workflow] Required inputs are missing.", "exit-fail", tabId);
    _workflowCliSetStatus("fail");
    return;
  }
  const commands = rendered.steps.map((step) => step.renderedCmd).filter(Boolean);
  if (!commands.length) {
    _workflowCliAppend("[workflow] No runnable steps.", "exit-fail", tabId);
    _workflowCliSetStatus("fail");
    return;
  }
  persistWorkflowInputValues(workflow, values);
  _workflowCliAppend(`[workflow] ${workflow.title}: ${commands.length} step(s) queued.`, "notice", tabId);
  runWorkflowCommands(commands);
}
function _workflowPromptForInputs(workflow, values, missing, tabId) {
  const queue = missing.slice();
  const askNext = () => {
    const input = queue.shift();
    if (!input) {
      _workflowRunResolved(workflow, values, tabId);
      return;
    }
    const label = input.label || input.id;
    const hint = input.placeholder ? ` (${input.placeholder})` : "";
    _workflowCliAppend(`[workflow] ${label}${hint}:`, "notice", tabId);
    const setPendingTerminalConfirm = typeof _setPendingTerminalConfirm === "function" && _setPendingTerminalConfirm || _workflowGlobalFunction("_setPendingTerminalConfirm");
    if (!setPendingTerminalConfirm) {
      _workflowCliAppend(`[workflow] missing --${input.id.replace(/_/g, "-")}`, "exit-fail", tabId);
      _workflowCliSetStatus("fail");
      return;
    }
    setPendingTerminalConfirm({
      kind: "text",
      tabId,
      onAnswer: async (answer) => {
        const value = sanitizeWorkflowInputValue(input, answer);
        if (!value) {
          queue.unshift(input);
        } else {
          values[input.id] = value;
        }
        askNext();
      },
      onCancel: async () => {
        _workflowCliAppend("[workflow] canceled.", "notice", tabId);
        _workflowCliSetStatus("idle");
      }
    });
    _workflowCliSetStatus("idle");
  };
  askNext();
}
async function handleWorkflowTerminalCommand(cmd, tabId = _workflowActiveTabId()) {
  const lines = [];
  const append = (text, cls = "") => {
    lines.push({ text, cls });
    _workflowCliAppend(text, cls, tabId);
  };
  const appendCommandEcho2 = typeof appendCommandEcho === "function" && appendCommandEcho || _workflowGlobalFunction("appendCommandEcho");
  if (appendCommandEcho2) appendCommandEcho2(cmd, tabId);
  if (!workflowCatalogItems.length) {
    try {
      await reloadWorkflowCatalog();
    } catch (err) {
      append(`[workflow] failed to load workflows: ${err.message || "network error"}`, "exit-fail");
      _workflowCliFinish(cmd, lines, "fail", tabId);
      return true;
    }
  }
  const parts = _workflowCommandTokens(cmd);
  const sub = String(parts[1] || "list").toLowerCase();
  if (sub === "help" || sub === "--help" || sub === "-h") {
    _workflowCliUsageLines().forEach((line) => append(line, ""));
    _workflowCliFinish(cmd, lines, "ok", tabId, { record: true });
    return true;
  }
  if (sub === "list" || parts.length === 1) {
    append("Workflows:", "builtin-section");
    workflowCatalogItems.forEach((workflow) => {
      const kind = workflow.source === "user" ? "user" : "built-in";
      const idHint = workflow.source === "user" && workflow.id ? `, id: ${workflow.id}` : "";
      append(`  ${workflowCliName(workflow)}  ${workflow.title} (${workflow.steps?.length || 0} steps, ${kind}${idHint})`, "builtin-help-row");
    });
    _workflowCliFinish(cmd, lines, "ok", tabId, { record: true });
    return true;
  }
  if (sub === "show") {
    const selector = parts.slice(2).join(" ");
    const { workflow, error } = _workflowFind(selector);
    if (!workflow) {
      append(`[workflow] ${error}`, "exit-fail");
      _workflowCliFinish(cmd, lines, "fail", tabId);
      return true;
    }
    append(`${workflow.title} (${workflowCliName(workflow)})`, "builtin-section");
    if (workflow.description) append(workflow.description, "builtin-note");
    (workflow.inputs || []).forEach((input) => append(`  --${input.id.replace(/_/g, "-")}  ${input.label || input.id}`, "builtin-help-row"));
    (workflow.steps || []).forEach((step, index) => {
      append(`  ${index + 1}. ${step.cmd}`, "builtin-help-row");
      if (step.note) append(`     ${step.note}`, "builtin-note");
    });
    _workflowCliFinish(cmd, lines, "ok", tabId, { record: true });
    return true;
  }
  if (sub === "run") {
    const parsed = _workflowParseRunArgs(parts.slice(2));
    if (parsed.errors.length) {
      parsed.errors.forEach((error2) => append(`[workflow] ${error2}`, "exit-fail"));
      _workflowCliFinish(cmd, lines, "fail", tabId);
      return true;
    }
    const { workflow, error } = _workflowFind(parsed.selector);
    if (!workflow) {
      append(`[workflow] ${error}`, "exit-fail");
      _workflowCliFinish(cmd, lines, "fail", tabId);
      return true;
    }
    const values = _workflowResolvedValues(workflow, parsed.values);
    const missing = _workflowMissingInputs(workflow, values);
    if (missing.length) {
      _workflowPromptForInputs(workflow, values, missing, tabId);
      return true;
    }
    _workflowRunResolved(workflow, values, tabId);
    return true;
  }
  append(`[workflow] unknown subcommand '${sub}'`, "exit-fail");
  _workflowCliUsageLines().forEach((line) => append(line, ""));
  _workflowCliFinish(cmd, lines, "fail", tabId);
  return true;
}
function _workflowRuntimeHintFor(workflow) {
  const value = workflowCliName(workflow);
  return _workflowRuntimeHint(value, workflow.title || value, value);
}
function _workflowInputHint(input) {
  const item = _workflowRuntimePlaceholderHint(
    `<${input.id}>`,
    input.label || input.id
  );
  if (input.type === "domain") item.value_type = "domain";
  return item;
}
function _runtimeWorkflowContext() {
  const workflows = Array.isArray(workflowCatalogItems) ? workflowCatalogItems : [];
  const workflowHints = workflows.map(_workflowRuntimeHintFor);
  const flags = [];
  const expectsValue = [];
  const argHints = {
    list: [],
    show: workflowHints,
    run: workflowHints,
    __positional__: [
      _workflowRuntimeHint("list", "List workflows"),
      _workflowRuntimeHint("show", "Show workflow steps", "show "),
      _workflowRuntimeHint("run", "Run a workflow", "run ")
    ]
  };
  const sequenceArgHints = {};
  const seenFlags = /* @__PURE__ */ new Set();
  workflows.forEach((workflow) => {
    const workflowName = workflowCliName(workflow).toLowerCase();
    const workflowFlags = [];
    (workflow.inputs || []).forEach((input) => {
      const flag = `--${String(input.id || "").replace(/_/g, "-")}`;
      if (!seenFlags.has(flag)) {
        seenFlags.add(flag);
        flags.push({ value: flag, description: input.label || input.id });
        expectsValue.push(flag);
        argHints[flag] = [_workflowInputHint(input)];
      }
      workflowFlags.push(_workflowRuntimeHint(flag, input.label || input.id, `${flag} `));
    });
    sequenceArgHints[`run ${workflowName}`] = workflowFlags;
  });
  return _workflowRuntimeContextSpec({ flags, expectsValue, argHints, sequenceArgHints });
}
document.querySelectorAll("#workflow-new-btn, #rail-workflow-new-btn").forEach((btn) => {
  if (btn.dataset.workflowEditorOpenBound === "1") return;
  btn.dataset.workflowEditorOpenBound = "1";
  btn.addEventListener("click", () => openWorkflowEditor());
});
document.getElementById("workflow-editor-add-step")?.addEventListener("click", () => addWorkflowEditorStep());
document.getElementById("workflow-editor-form")?.addEventListener("submit", (event) => {
  event.preventDefault();
  saveWorkflowEditor();
});
document.querySelectorAll(".workflow-editor-close").forEach((btn) => {
  btn.addEventListener("click", () => closeWorkflowEditor());
});
document.getElementById("workflow-editor-overlay")?.addEventListener("click", (event) => {
  if (event.target === event.currentTarget) closeWorkflowEditor();
});
if (typeof window !== "undefined") {
  if (workflowCatalogItems.length) renderWorkflowItems(workflowCatalogItems, { emitCatalogEvent: false });
  if (typeof setWorkflowHandlers === "function") {
    setWorkflowHandlers({
      renderWorkflowItems,
      reloadWorkflowCatalog,
      ensureWorkflowCatalogLoaded,
      handleWorkflowTerminalCommand,
      _runtimeWorkflowContext,
      openWorkflowEditor,
      closeWorkflowEditor
    });
  }
}

export {
  openWorkflowEditor,
  closeWorkflowEditor,
  renderWorkflowItems,
  reloadWorkflowCatalog,
  ensureWorkflowCatalogLoaded,
  handleWorkflowTerminalCommand,
  _runtimeWorkflowContext
};
