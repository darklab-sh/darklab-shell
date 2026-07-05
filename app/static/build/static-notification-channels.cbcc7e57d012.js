import {
  apiFetch
} from "./static-chunk-5i2t3zlu.acdd7b56baea.js";
import {
  showToast
} from "./static-chunk-poi5czx6.3f5c94749765.js";
import "./static-chunk-zpenfczu.1862ffb66041.js";
import {
  showConfirm
} from "./static-chunk-4m44pm74.0a8001fa1d52.js";
import "./static-chunk-2bgb52uq.a327269283bb.js";
import "./static-chunk-yo5cjr7d.b86e0c93eff0.js";
import "./static-chunk-gwztcp24.e58b5ff85d88.js";
import "./static-chunk-2kxtimik.c9801087c7a7.js";

// app/static/js/features/preferences/notification_channels.js
var exportedRefreshNotificationChannels = null;
var exportedOpenNotificationChannelEditor = null;
(function(global) {
  let _channelKinds = [];
  let _triggers = [];
  let _kindContract = null;
  let _kindContractLoading = null;
  let _channelsCache = null;
  let _channelsLoading = false;
  const _deliveryPanels = /* @__PURE__ */ new Set();
  const _deliveryCache = /* @__PURE__ */ new Map();
  const _deliveryLoading = /* @__PURE__ */ new Set();
  let _bound = false;
  function _el(id) {
    return document.getElementById(id);
  }
  function _apiFetch() {
    return typeof apiFetch === "function" && apiFetch || (typeof global.fetch === "function" ? global.fetch.bind(global) : null);
  }
  function _msg(text, { error = false } = {}) {
    const node = _el("options-notification-msg");
    if (!node) return;
    node.textContent = text || "";
    node.classList.toggle("is-error", !!error);
    node.style.display = text ? "" : "none";
  }
  function _toast(text, tone = "success") {
    _msg("");
    const toast = typeof showToast === "function" ? showToast : null;
    if (typeof toast === "function") {
      toast(text, tone);
      return;
    }
    _msg(text, { error: tone === "error" });
  }
  function _setBusy(busy) {
    _channelsLoading = !!busy;
    ["options-notification-refresh-btn", "options-notification-new-btn"].forEach((id) => {
      const button = _el(id);
      if (button) button.disabled = _channelsLoading;
    });
  }
  function _titleize(value) {
    return String(value || "Channel").replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
  }
  function _setKindContract(data) {
    const kinds = Array.isArray(data?.kinds) ? data.kinds : [];
    _kindContract = {
      kinds: kinds.filter((item) => item && typeof item === "object" && item.kind),
      triggers: Array.isArray(data?.triggers) ? data.triggers : []
    };
    _channelKinds = _kindContract.kinds.map((item) => ({
      value: String(item.kind),
      label: String(item.label || _titleize(item.kind))
    }));
    _triggers = _kindContract.triggers.map((item) => ({
      value: String(item.value || ""),
      label: String(item.label || _titleize(item.value))
    })).filter((item) => item.value);
  }
  async function _ensureKindContract() {
    if (_kindContract) return _kindContract;
    if (_kindContractLoading) return _kindContractLoading;
    _kindContractLoading = (async () => {
      const resp = await _apiFetch()("/session/notification-channel-kinds");
      const data = await resp.json().catch(() => ({}));
      if (resp && resp.ok === false) throw new Error(data.message || data.error || `HTTP ${resp.status}`);
      _setKindContract(data);
      return _kindContract;
    })();
    try {
      return await _kindContractLoading;
    } finally {
      _kindContractLoading = null;
    }
  }
  function _kindDefinition(kind) {
    return (_kindContract?.kinds || []).find((item) => item.kind === kind) || null;
  }
  function _secretFields(kind) {
    return Array.isArray(_kindDefinition(kind)?.secret_fields) ? _kindDefinition(kind).secret_fields : [];
  }
  function _configFields(kind) {
    return Array.isArray(_kindDefinition(kind)?.config_fields) ? _kindDefinition(kind).config_fields : [];
  }
  function _kindLabel(kind) {
    return _channelKinds.find((item) => item.value === kind)?.label || _titleize(kind);
  }
  function _secretConfigured(channel, name) {
    return (channel.secret_fields || []).some((field) => field.name === name && field.configured);
  }
  function _deliveryStatusLabel(status) {
    return String(status || "pending").replaceAll("_", " ");
  }
  function _deliveryStatusClass(status) {
    if (status === "sent") return "badge-tone-green";
    if (status === "dead") return "badge-tone-red";
    if (status === "retry_wait") return "badge-tone-amber";
    return "badge-tone-muted";
  }
  function _formatDeliveryTime(value) {
    const raw = String(value || "").trim();
    if (!raw) return "";
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return raw;
    return date.toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    });
  }
  function _shortRunId(runId) {
    const value = String(runId || "").trim();
    return value ? value.slice(0, 8) : "";
  }
  function _eventTitle(event) {
    const trigger = String(event.trigger || "notification").replaceAll("_", " ");
    const digest = event.project_digest || {};
    const projectName = String(digest.project_name || "").trim();
    if (event.trigger === "project_digest" && projectName) {
      return `${trigger}: ${projectName}`;
    }
    return trigger;
  }
  function _eventDigestMeta(event) {
    const digest = event.project_digest || {};
    if (event.trigger !== "project_digest" || !digest.window_start || !digest.window_end) return "";
    return `window ${_formatDeliveryTime(digest.window_start)} - ${_formatDeliveryTime(digest.window_end)}`;
  }
  function _eventMeta(event) {
    const parts = [];
    const digestMeta = _eventDigestMeta(event);
    if (digestMeta) parts.push(digestMeta);
    const runId = _shortRunId(event.run_id);
    if (runId) parts.push(`run ${runId}`);
    if (event.attempts) parts.push(`${event.attempts} attempt${event.attempts === 1 ? "" : "s"}`);
    const timestamp = _formatDeliveryTime(event.last_attempt_at || event.created);
    if (timestamp) parts.push(timestamp);
    if (event.next_attempt_at && event.status === "retry_wait") {
      parts.push(`retry ${_formatDeliveryTime(event.next_attempt_at)}`);
    }
    return parts.join(" · ");
  }
  function _deliveryEventRow(event) {
    const row = document.createElement("div");
    row.className = "options-notification-event-row";
    const badge = document.createElement("span");
    badge.className = `badge ${_deliveryStatusClass(event.status)} options-secret-chip`;
    badge.textContent = _deliveryStatusLabel(event.status);
    const main = document.createElement("div");
    main.className = "options-notification-event-main";
    const title = document.createElement("div");
    title.className = "options-notification-event-title";
    title.textContent = _eventTitle(event);
    const meta = document.createElement("div");
    meta.className = "options-secret-meta";
    meta.textContent = _eventMeta(event);
    main.append(title, meta);
    if (event.last_error) {
      const error = document.createElement("div");
      error.className = "options-notification-event-error";
      error.textContent = event.last_error;
      main.appendChild(error);
    }
    row.append(badge, main);
    return row;
  }
  function _renderDeliveryPanel(channel) {
    const panel = document.createElement("div");
    panel.className = "options-notification-deliveries";
    panel.dataset.notificationDeliveries = channel.id;
    const header = document.createElement("div");
    header.className = "options-notification-deliveries-header";
    const title = document.createElement("div");
    title.className = "options-notification-deliveries-title";
    title.textContent = "Recent deliveries";
    const refresh = document.createElement("button");
    refresh.type = "button";
    refresh.className = "btn btn-secondary btn-compact";
    refresh.textContent = "Refresh";
    refresh.disabled = _deliveryLoading.has(channel.id);
    refresh.addEventListener("click", () => refreshNotificationChannelDeliveries(channel, { force: true }));
    header.append(title, refresh);
    panel.appendChild(header);
    if (_deliveryLoading.has(channel.id)) {
      const loading = document.createElement("div");
      loading.className = "options-secret-meta";
      loading.textContent = "Loading recent deliveries...";
      panel.appendChild(loading);
      return panel;
    }
    const data = _deliveryCache.get(channel.id);
    if (data?.error) {
      const error = document.createElement("div");
      error.className = "options-secret-meta is-error";
      error.textContent = `Could not load deliveries: ${data.error}`;
      panel.appendChild(error);
      return panel;
    }
    const events = Array.isArray(data?.events) ? data.events : [];
    if (!events.length) {
      const empty = document.createElement("div");
      empty.className = "options-secret-meta";
      empty.textContent = "No deliveries recorded for this channel yet.";
      panel.appendChild(empty);
      return panel;
    }
    const list = document.createElement("div");
    list.className = "options-notification-event-list";
    events.forEach((event) => list.appendChild(_deliveryEventRow(event)));
    panel.appendChild(list);
    return panel;
  }
  function _field(label, input) {
    const wrapper = document.createElement("label");
    wrapper.className = "options-secret-field";
    const text = document.createElement("span");
    text.className = "options-secret-field-label";
    text.textContent = label;
    wrapper.append(text, input);
    return wrapper;
  }
  function _input(value = "", attrs = {}) {
    const input = document.createElement("input");
    input.className = "form-control form-control-compact options-token-input";
    input.type = attrs.type || "text";
    input.value = value || "";
    Object.entries(attrs).forEach(([key, attrValue]) => {
      if (key !== "type") input.setAttribute(key, attrValue);
    });
    return input;
  }
  function _select(value, options, attrs = {}) {
    const select = document.createElement("select");
    select.className = "form-select";
    Object.entries(attrs).forEach(([key, attrValue]) => select.setAttribute(key, attrValue));
    options.forEach((option) => {
      const node = document.createElement("option");
      node.value = option.value;
      node.textContent = option.label;
      select.appendChild(node);
    });
    select.value = value || options[0]?.value || "";
    return select;
  }
  function _triggerChecks(selected) {
    const selectedSet = new Set(Array.isArray(selected) && selected.length ? selected : ["run_complete"]);
    const wrapper = document.createElement("div");
    wrapper.className = "options-secret-field";
    const label = document.createElement("div");
    label.className = "options-secret-field-label";
    label.textContent = "Triggers";
    const list = document.createElement("div");
    list.className = "form-fieldset";
    _triggers.forEach((trigger) => {
      const row = document.createElement("label");
      row.className = "form-check";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = trigger.value;
      input.checked = selectedSet.has(trigger.value);
      const text = document.createElement("span");
      text.textContent = trigger.label;
      row.append(input, text);
      list.appendChild(row);
    });
    wrapper.append(label, list);
    return { wrapper, list };
  }
  function _channelConfigSummary(channel) {
    const config = channel.config || {};
    if (channel.kind === "email" && Array.isArray(config.recipients) && config.recipients.length) {
      return `${config.recipients.length} recipients`;
    }
    if (channel.kind === "telegram" && config.chat_id) return `chat ${config.chat_id}`;
    return "";
  }
  function _renderChannels(channels) {
    const list = _el("options-notification-list");
    if (!list) return;
    list.innerHTML = "";
    if (!Array.isArray(channels) || channels.length === 0) {
      const empty = document.createElement("div");
      empty.className = "options-secret-empty options-secret-empty-state";
      const title = document.createElement("div");
      title.textContent = "No notification channels yet.";
      const hint = document.createElement("div");
      hint.className = "options-secret-meta";
      hint.textContent = "Add a channel to get pinged when long runs finish.";
      empty.append(title, hint);
      list.appendChild(empty);
      return;
    }
    channels.forEach((channel) => {
      const row = document.createElement("div");
      row.className = "options-secret-row";
      const body = document.createElement("div");
      body.className = "options-secret-row-body";
      const name = document.createElement("div");
      name.className = "options-secret-name";
      name.textContent = channel.label || _kindLabel(channel.kind);
      const chips = document.createElement("div");
      chips.className = "options-secret-chips";
      [
        { text: _kindLabel(channel.kind), className: "badge badge-tone-muted options-secret-chip" },
        {
          text: channel.muted ? "muted" : "active",
          className: `badge ${channel.muted ? "badge-tone-muted is-muted" : "badge-tone-green"} options-secret-chip`
        }
      ].forEach((chipConfig) => {
        const chip = document.createElement("span");
        chip.className = chipConfig.className;
        chip.textContent = chipConfig.text;
        chips.appendChild(chip);
      });
      const meta = document.createElement("div");
      meta.className = "options-secret-meta";
      const summary = _channelConfigSummary(channel);
      const triggers = (channel.triggers || []).map((trigger) => trigger.replaceAll("_", " ")).join(", ") || "run complete";
      meta.textContent = [triggers, summary].filter(Boolean).join(" · ");
      body.append(name, chips, meta);
      const actions = document.createElement("div");
      actions.className = "options-secret-actions";
      const mute = document.createElement("button");
      mute.type = "button";
      mute.className = "btn btn-secondary btn-compact";
      mute.textContent = channel.muted ? "Unmute" : "Mute";
      mute.addEventListener("click", () => toggleNotificationChannelMuted(channel));
      const test = document.createElement("button");
      test.type = "button";
      test.className = "btn btn-secondary btn-compact";
      test.textContent = "Test";
      test.addEventListener("click", () => testNotificationChannel(channel));
      const deliveries = document.createElement("button");
      deliveries.type = "button";
      deliveries.className = "btn btn-secondary btn-compact";
      deliveries.textContent = "Deliveries";
      deliveries.setAttribute("aria-expanded", _deliveryPanels.has(channel.id) ? "true" : "false");
      deliveries.addEventListener("click", () => toggleNotificationChannelDeliveries(channel));
      const edit = document.createElement("button");
      edit.type = "button";
      edit.className = "btn btn-secondary btn-compact";
      edit.textContent = "Edit";
      edit.addEventListener("click", () => openNotificationChannelEditor(channel));
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "btn btn-destructive btn-compact";
      remove.textContent = "Delete";
      remove.addEventListener("click", () => deleteNotificationChannel(channel));
      actions.append(mute, test, deliveries, edit, remove);
      row.append(body, actions);
      if (_deliveryPanels.has(channel.id)) {
        row.appendChild(_renderDeliveryPanel(channel));
      }
      list.appendChild(row);
    });
  }
  async function refreshNotificationChannelDeliveries(channel, { force = false } = {}) {
    if (!channel?.id) return null;
    if (_deliveryLoading.has(channel.id) && !force) return _deliveryCache.get(channel.id) || null;
    if (_deliveryCache.has(channel.id) && !force) {
      _renderChannels(_channelsCache || []);
      return _deliveryCache.get(channel.id);
    }
    _deliveryLoading.add(channel.id);
    _renderChannels(_channelsCache || []);
    try {
      const url = `/session/notification-events?channel_id=${encodeURIComponent(channel.id)}&limit=5`;
      const resp = await _apiFetch()(url);
      const data = await resp.json().catch(() => ({}));
      if (resp && resp.ok === false) throw new Error(data.message || data.error || `HTTP ${resp.status}`);
      const payload = { ...data, events: Array.isArray(data.events) ? data.events : [] };
      _deliveryCache.set(channel.id, payload);
      return payload;
    } catch (error) {
      _deliveryCache.set(channel.id, { events: [], error: error.message || "network error" });
      return _deliveryCache.get(channel.id);
    } finally {
      _deliveryLoading.delete(channel.id);
      _renderChannels(_channelsCache || []);
    }
  }
  async function toggleNotificationChannelDeliveries(channel) {
    if (!channel?.id) return;
    if (_deliveryPanels.has(channel.id)) {
      _deliveryPanels.delete(channel.id);
      _renderChannels(_channelsCache || []);
      return;
    }
    _deliveryPanels.add(channel.id);
    await refreshNotificationChannelDeliveries(channel);
  }
  async function refreshNotificationChannels({ force = false } = {}) {
    if (_channelsLoading && !force) return _channelsCache || [];
    if (_channelsCache && !force) {
      _renderChannels(_channelsCache);
      _msg("");
      return _channelsCache;
    }
    _setBusy(true);
    try {
      const resp = await _apiFetch()("/session/notification-channels");
      const data = await resp.json().catch(() => ({}));
      if (resp && resp.ok === false) throw new Error(data.message || data.error || `HTTP ${resp.status}`);
      _channelsCache = Array.isArray(data.channels) ? data.channels : [];
      _renderChannels(_channelsCache);
      _msg("");
      return _channelsCache;
    } catch (error) {
      if (_channelsCache) {
        _renderChannels(_channelsCache);
      } else {
        _renderChannels([]);
      }
      const message = error.message === "session_token_required" ? "Generate or set a session token before adding notification channels." : `Could not load notification channels: ${error.message || "network error"}`;
      _msg(message, { error: true });
      return [];
    } finally {
      _setBusy(false);
    }
  }
  function _buildEditor(channel) {
    const content = document.createElement("div");
    content.className = "form-fieldset";
    const kindSelect = _select(channel?.kind || _channelKinds[0]?.value || "webhook", _channelKinds, {
      "aria-label": "Notification channel type"
    });
    kindSelect.disabled = !!channel;
    const labelInput = _input(channel?.label || "", {
      maxlength: "80",
      autocomplete: "off",
      placeholder: "Label"
    });
    const dynamicFields = document.createElement("div");
    const error = document.createElement("div");
    error.className = "form-error";
    error.style.display = "none";
    const triggerControls = _triggerChecks(channel?.triggers || ["run_complete"]);
    content.append(
      _field("Type", kindSelect),
      _field("Label", labelInput),
      dynamicFields,
      triggerControls.wrapper,
      error
    );
    const renderDynamicFields = () => {
      dynamicFields.innerHTML = "";
      const kind = kindSelect.value;
      _secretFields(kind).forEach((field) => {
        const input = _input("", {
          type: "password",
          autocomplete: "off",
          placeholder: channel && _secretConfigured(channel, field.name) ? "Leave blank to keep existing" : field.label
        });
        input.dataset.secretField = field.name;
        dynamicFields.appendChild(_field(field.label, input));
      });
      _configFields(kind).forEach((field) => {
        const value = field.name === "recipients" && Array.isArray(channel?.config?.recipients) ? channel.config.recipients.join(", ") : channel?.config?.[field.name] || "";
        const input = _input(value, {
          autocomplete: "off",
          placeholder: field.optional ? "Optional" : field.label
        });
        input.dataset.configField = field.name;
        dynamicFields.appendChild(_field(field.label, input));
        if (field.help) {
          const help = document.createElement("div");
          help.className = "options-secret-meta";
          help.textContent = field.help;
          dynamicFields.appendChild(help);
        }
      });
    };
    kindSelect.addEventListener("change", renderDynamicFields);
    renderDynamicFields();
    return { content, kindSelect, labelInput, dynamicFields, triggerControls, error };
  }
  function _readEditor(editor, channel) {
    const kind = editor.kindSelect.value;
    const secretValues = {};
    editor.dynamicFields.querySelectorAll("[data-secret-field]").forEach((input) => {
      if (input.value) secretValues[input.dataset.secretField] = input.value;
    });
    const config = {};
    editor.dynamicFields.querySelectorAll("[data-config-field]").forEach((input) => {
      const key = input.dataset.configField;
      const value = String(input.value || "").trim();
      if (!value) return;
      config[key] = key === "recipients" ? value.split(",").map((item) => item.trim()).filter(Boolean) : value;
    });
    const triggers = Array.from(editor.triggerControls.list.querySelectorAll('input[type="checkbox"]:checked')).map((input) => input.value);
    const missingSecret = _secretFields(kind).find((field) => !secretValues[field.name] && !(channel && channel.kind === kind && _secretConfigured(channel, field.name)));
    if (missingSecret) return { error: `${missingSecret.label} is required.` };
    return {
      kind,
      label: editor.labelInput.value,
      config,
      triggers,
      secret_values: secretValues,
      muted: !!channel?.muted
    };
  }
  async function _saveEditor(channel, editor) {
    editor.error.style.display = "none";
    const payload = _readEditor(editor, channel);
    if (payload.error) {
      editor.error.textContent = payload.error;
      editor.error.style.display = "";
      return false;
    }
    try {
      const url = channel ? `/session/notification-channels/${encodeURIComponent(channel.id)}` : "/session/notification-channels";
      const resp = await _apiFetch()(url, {
        method: channel ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await resp.json().catch(() => ({}));
      if (resp && resp.ok === false) throw new Error(data.message || data.error || `HTTP ${resp.status}`);
      _channelsCache = null;
      await refreshNotificationChannels({ force: true });
      _toast(channel ? "Notification channel updated." : "Notification channel added.");
      return true;
    } catch (error) {
      _toast(`Save failed: ${error.message || "network error"}`, "error");
      return false;
    }
  }
  async function openNotificationChannelEditor(channel = null) {
    const confirm = typeof showConfirm === "function" ? showConfirm : null;
    if (typeof confirm !== "function") return null;
    try {
      await _ensureKindContract();
    } catch (error) {
      _toast(`Could not load notification channel types: ${error.message || "network error"}`, "error");
      return null;
    }
    const editor = _buildEditor(channel);
    return confirm({
      body: {
        text: channel ? "Update notification channel." : "Add a notification channel.",
        note: "Secret values are sent once, stored in the vault, and never displayed again."
      },
      content: editor.content,
      defaultFocus: editor.labelInput,
      actions: [
        { id: "cancel", label: "Cancel", role: "cancel" },
        {
          id: "save",
          label: channel ? "Save" : "Add",
          role: "primary",
          onActivate: () => _saveEditor(channel, editor)
        }
      ]
    });
  }
  async function toggleNotificationChannelMuted(channel) {
    const payload = {
      kind: channel.kind,
      label: channel.label,
      config: channel.config || {},
      triggers: channel.triggers || ["run_complete"],
      muted: !channel.muted
    };
    _setBusy(true);
    try {
      const resp = await _apiFetch()(`/session/notification-channels/${encodeURIComponent(channel.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await resp.json().catch(() => ({}));
      if (resp && resp.ok === false) throw new Error(data.message || data.error || `HTTP ${resp.status}`);
      _channelsCache = null;
      await refreshNotificationChannels({ force: true });
      _toast(payload.muted ? "Notification channel muted." : "Notification channel unmuted.");
    } catch (error) {
      _toast(`Update failed: ${error.message || "network error"}`, "error");
    } finally {
      _setBusy(false);
    }
  }
  async function testNotificationChannel(channel) {
    _setBusy(true);
    try {
      const resp = await _apiFetch()(`/session/notification-channels/${encodeURIComponent(channel.id)}/test`, {
        method: "POST"
      });
      const data = await resp.json().catch(() => ({}));
      if (resp && resp.ok === false) throw new Error(data.message || data.error || `HTTP ${resp.status}`);
      const event = Array.isArray(data.events) ? data.events[0] : null;
      if (event?.status === "sent") {
        _toast("Test notification delivered.");
      } else if (event?.status === "retry_wait" || event?.status === "dead") {
        const detail = event.last_error ? `: ${event.last_error}` : ".";
        _toast(`Test notification failed${detail}`, "error");
      } else {
        _toast(
          data.queued ? "Test notification queued." : "No test notification was queued for this channel.",
          data.queued ? "success" : "error"
        );
      }
      if (_deliveryPanels.has(channel.id)) {
        await refreshNotificationChannelDeliveries(channel, { force: true });
      }
    } catch (error) {
      _toast(`Test failed: ${error.message || "network error"}`, "error");
    } finally {
      _setBusy(false);
    }
  }
  async function deleteNotificationChannel(channel) {
    const confirm = typeof showConfirm === "function" ? showConfirm : null;
    if (typeof confirm !== "function") return false;
    const choice = await confirm({
      body: {
        text: `Delete ${channel.label || _kindLabel(channel.kind)}?`,
        note: "The channel will stop receiving outbound notifications."
      },
      tone: "danger",
      actions: [
        { id: "cancel", label: "Cancel", role: "cancel" },
        { id: "delete", label: "Delete", role: "destructive" }
      ]
    });
    if (choice !== "delete") return false;
    _setBusy(true);
    try {
      const resp = await _apiFetch()(`/session/notification-channels/${encodeURIComponent(channel.id)}`, {
        method: "DELETE"
      });
      const data = await resp.json().catch(() => ({}));
      if (resp && resp.ok === false) throw new Error(data.message || data.error || `HTTP ${resp.status}`);
      _deliveryPanels.delete(channel.id);
      _deliveryCache.delete(channel.id);
      _channelsCache = null;
      await refreshNotificationChannels({ force: true });
      _toast("Notification channel deleted.");
      return true;
    } catch (error) {
      _toast(`Delete failed: ${error.message || "network error"}`, "error");
      return false;
    } finally {
      _setBusy(false);
    }
  }
  function bindNotificationChannelsPanel() {
    if (_bound) return;
    _bound = true;
    _el("options-notification-refresh-btn")?.addEventListener("click", () => refreshNotificationChannels({ force: true }));
    _el("options-notification-new-btn")?.addEventListener("click", () => openNotificationChannelEditor());
    if (!document.querySelector('[data-options-panel="notifications"]')?.hidden) {
      refreshNotificationChannels();
    }
  }
  bindNotificationChannelsPanel();
  exportedRefreshNotificationChannels = refreshNotificationChannels;
  exportedOpenNotificationChannelEditor = openNotificationChannelEditor;
})(typeof window !== "undefined" ? window : globalThis);
export {
  exportedOpenNotificationChannelEditor as openNotificationChannelEditor,
  exportedRefreshNotificationChannels as refreshNotificationChannels
};
