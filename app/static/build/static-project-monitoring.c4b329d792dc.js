import {
  hasHistoryRunModalStateHandler,
  openHistoryRunDetails
} from "./static-chunk-jdmxosyg.f57815afbc1f.js";
import {
  fetchAndRenderHistoryComparison,
  hasHistoryCompareHandler
} from "./static-chunk-iqwevzke.cb2ae1f8735e.js";

// app/static/js/features/projects/project_monitoring.js
var exportedDarklabProjectMonitoring = null;
(function projectMonitoringModule(global) {
  "use strict";
  const countItems = [
    ["active", "Active"],
    ["changed", "Changed"],
    ["failed", "Failed"],
    ["quiet", "Quiet"],
    ["paused", "Paused"]
  ];
  const stateLabels = {
    active: "Active",
    changed: "Changed",
    failed: "Failed",
    quiet: "Quiet",
    paused: "Paused"
  };
  const fireKindLabels = {
    baseline_accepted: "Baseline accepted",
    baseline_created: "Baseline created",
    changed: "Changed",
    failed: "Failed",
    no_change: "No change",
    paused: "Paused",
    recovered: "Recovered",
    unclassified: "Unclassified"
  };
  const timelineFireKindsByState = {
    active: /* @__PURE__ */ new Set(["baseline_accepted", "baseline_created", "no_change", "recovered", "unclassified"]),
    changed: /* @__PURE__ */ new Set(["changed"]),
    failed: /* @__PURE__ */ new Set(["failed"]),
    quiet: /* @__PURE__ */ new Set(["no_change", "recovered"]),
    paused: /* @__PURE__ */ new Set(["paused"])
  };
  const severityLabels = {
    critical: "Critical",
    important: "Important",
    informational: "Info",
    none: "No signal"
  };
  const ackLabels = {
    new: "New",
    acknowledged: "Acknowledged",
    expected: "Expected",
    needs_action: "Needs action",
    resolved: "Resolved"
  };
  function createProjectMonitoringController(context) {
    const ctx = context || {};
    const states = /* @__PURE__ */ new Map();
    function defaultState() {
      return {
        counts: {},
        canManageDigestSettings: true,
        digestChannels: [],
        digestSettings: null,
        error: "",
        loaded: false,
        loading: false,
        filterOptions: {},
        filters: {},
        monitors: [],
        project: null,
        quietNoChangeThreshold: 3,
        timeline: []
      };
    }
    function stateFor(projectId) {
      const id = String(projectId || "");
      if (!states.has(id)) states.set(id, defaultState());
      return states.get(id);
    }
    function invalidate(projectId = "") {
      const normalized = String(projectId || "");
      if (normalized) states.delete(normalized);
      else states.clear();
    }
    async function responseError(resp, fallback) {
      if (typeof ctx.projectResponseError === "function") return ctx.projectResponseError(resp, fallback);
      return new Error(fallback);
    }
    function logClientEvent(eventName, err, details = {}) {
      if (typeof ctx.logClientError !== "function") return;
      const payload = {
        page: "project_monitoring",
        ...details
      };
      ctx.logClientError(`${eventName} ${JSON.stringify(payload)}`, err);
    }
    async function load(projectId, options = {}) {
      const normalized = String(projectId || "");
      if (!normalized) return false;
      const st = stateFor(normalized);
      if (st.loaded && options.force !== true) return true;
      st.loading = true;
      st.error = "";
      if (options.render !== false) ctx.renderProjectExplorer?.();
      try {
        const resp = await ctx.projectWorkspaceRequest(
          `/projects/${encodeURIComponent(normalized)}/monitoring?fire_limit=8`,
          { cache: "no-store" }
        );
        if (!resp.ok) throw await responseError(resp, "Could not load project monitoring.");
        const payload = await resp.json();
        st.counts = payload && typeof payload.counts === "object" ? payload.counts : {};
        st.canManageDigestSettings = payload?.can_manage_digest_settings !== false;
        st.digestChannels = Array.isArray(payload?.notification_channels) ? payload.notification_channels : [];
        st.digestSettings = payload && typeof payload.digest_settings === "object" ? payload.digest_settings : null;
        st.filterOptions = payload && typeof payload.filter_options === "object" ? payload.filter_options : {};
        st.monitors = Array.isArray(payload.monitors) ? payload.monitors : [];
        st.project = payload && typeof payload.project === "object" ? payload.project : null;
        st.quietNoChangeThreshold = Math.max(1, Number(payload.quiet_no_change_threshold || 3) || 3);
        st.timeline = Array.isArray(payload.timeline) ? payload.timeline : [];
        st.loaded = true;
      } catch (err) {
        st.error = err && err.message ? err.message : "Could not load project monitoring.";
        logClientEvent("PROJECT_MONITORING_CLIENT_LOAD_FAILED", err, {
          phase: "load",
          selection_key: `project:${normalized}`
        });
      } finally {
        st.loading = false;
        if (options.render !== false) {
          ctx.renderProjectExplorer?.();
          if (ctx.mobileView?.() === "detail") ctx.renderProjectMobileDetail?.();
        }
      }
      return st.loaded;
    }
    function labelForFireKind(kind) {
      return fireKindLabels[String(kind || "unclassified")] || fireKindLabels.unclassified;
    }
    function labelForState(state) {
      return stateLabels[String(state || "active")] || stateLabels.active;
    }
    function labelForSeverity(severity) {
      return severityLabels[String(severity || "none")] || severityLabels.none;
    }
    function labelForAck(state) {
      return ackLabels[String(state || "new")] || ackLabels.new;
    }
    function stateTone(state) {
      const normalized = String(state || "active");
      if (normalized === "changed") return "badge-tone-amber";
      if (normalized === "failed") return "badge-tone-red";
      if (normalized === "active" || normalized === "quiet") return "badge-tone-green";
      return "badge-tone-muted";
    }
    function fireKindTone(kind) {
      const normalized = String(kind || "unclassified");
      if (normalized === "changed") return "badge-tone-amber";
      if (normalized === "failed") return "badge-tone-red";
      if (normalized === "no_change" || normalized === "recovered") return "badge-tone-green";
      return "badge-tone-muted";
    }
    function severityTone(severity) {
      const normalized = String(severity || "none");
      if (normalized === "critical") return "badge-tone-red";
      if (normalized === "important") return "badge-tone-amber";
      return "badge-tone-muted";
    }
    function ackTone(state) {
      const normalized = String(state || "new");
      if (normalized === "acknowledged" || normalized === "needs_action") return "badge-tone-amber";
      if (normalized === "expected" || normalized === "resolved") return "badge-tone-green";
      return "badge-tone-muted";
    }
    function optionLabel(kind, value) {
      if (kind === "status") return labelForState(value);
      if (kind === "severity") return labelForSeverity(value);
      if (kind === "ack") return labelForAck(value);
      return String(value || "");
    }
    function filterValue(st, key) {
      return String(st.filters?.[key] || "");
    }
    function fireSeverity(fire) {
      return String((fire?.rollup || {}).severity || "");
    }
    function fireClassifier(fire) {
      return String((fire?.rollup || {}).classifier || "");
    }
    function monitorSeverity(monitor) {
      const severities = [monitor.latest_fire, ...Array.isArray(monitor.fires) ? monitor.fires : []].map(fireSeverity).filter(Boolean);
      if (severities.includes("critical")) return "critical";
      if (severities.includes("important")) return "important";
      if (severities.includes("informational")) return "informational";
      return severities[0] || "";
    }
    function monitorClassifier(monitor) {
      return fireClassifier(monitor.latest_fire) || (Array.isArray(monitor.fires) ? monitor.fires.map(fireClassifier).find(Boolean) : "") || String(monitor.monitor_group?.key || "");
    }
    function itemTargetValues(item) {
      return (Array.isArray(item?.linked_targets) ? item.linked_targets : []).map((target) => String(target?.value || "")).filter(Boolean);
    }
    function createdWithin(value, days) {
      const count = Number(days || 0);
      if (!Number.isFinite(count) || count <= 0) return true;
      const parsed = Date.parse(String(value || ""));
      if (!Number.isFinite(parsed)) return false;
      return parsed >= Date.now() - count * 24 * 60 * 60 * 1e3;
    }
    function fireMatchesStatus(fire, status) {
      const normalized = String(status || "");
      if (!normalized) return true;
      const fireKind = String(fire?.fire_kind || "unclassified");
      const allowedKinds = timelineFireKindsByState[normalized];
      if (!allowedKinds) return fireKind === normalized;
      return allowedKinds.has(fireKind);
    }
    function matchesMonitor(monitor, filters) {
      if (filters.status && String(monitor.dashboard_state || "") !== filters.status) return false;
      if (filters.severity && monitorSeverity(monitor) !== filters.severity) return false;
      if (filters.classifier && monitorClassifier(monitor) !== filters.classifier) return false;
      if (filters.cadence && String(monitor.schedule?.cadence_preset || "") !== filters.cadence) return false;
      if (filters.ack && String(monitor.current_triage_state || "") !== filters.ack) return false;
      if (filters.group && String(monitor.monitor_group?.key || "") !== filters.group) return false;
      if (filters.target && !itemTargetValues(monitor).includes(filters.target)) return false;
      if (filters.changed_since && !createdWithin(monitor.latest_fire?.created, filters.changed_since)) return false;
      return true;
    }
    function matchesFire(fire, filters) {
      if (filters.status && !fireMatchesStatus(fire, filters.status)) return false;
      if (filters.severity && fireSeverity(fire) !== filters.severity) return false;
      if (filters.classifier && fireClassifier(fire) !== filters.classifier) return false;
      if (filters.ack && String(fire.ack_state || "new") !== filters.ack) return false;
      if (filters.group && String(fire.monitor_group?.key || "") !== filters.group) return false;
      if (filters.target && !itemTargetValues(fire).includes(filters.target)) return false;
      if (filters.changed_since && !createdWithin(fire.created, filters.changed_since)) return false;
      return true;
    }
    function runLabel(run, fallback = "") {
      if (!run || typeof run !== "object") return fallback || "Run unavailable";
      return String(run.command || run.id || fallback || "Run");
    }
    function cadenceLabel(schedule) {
      if (!schedule || typeof schedule !== "object") return "";
      return String(schedule.cadence_preset || schedule.cron_expr || "").trim();
    }
    function formatDateLabel(value) {
      const normalized = String(value || "").trim();
      if (!normalized) return "";
      return ctx.formatDate ? ctx.formatDate(normalized) : normalized;
    }
    function runMetaLabel(prefix, run, fallback = "") {
      const fallbackId = String(fallback || run?.id || "").trim();
      if (run && typeof run === "object") return `${prefix}: ${runLabel(run, fallbackId)}`;
      if (fallbackId) return `${prefix}: ${fallbackId} unavailable`;
      return "";
    }
    function lastChangeDate(monitor) {
      const triage = monitor.current_triage_fire;
      if (triage && ["changed", "failed"].includes(String(triage.fire_kind || ""))) return triage.created;
      const latest = monitor.latest_fire;
      if (latest && ["changed", "failed", "recovered"].includes(String(latest.fire_kind || ""))) return latest.created;
      return "";
    }
    function appendMeta(parent, parts) {
      const meta = document.createElement("div");
      meta.className = "project-monitoring-meta";
      meta.textContent = parts.map((part) => String(part || "").trim()).filter(Boolean).join(" · ");
      if (meta.textContent) parent.appendChild(meta);
    }
    function digestSettingsOrDefault(st) {
      const settings = st.digestSettings && typeof st.digestSettings === "object" ? st.digestSettings : {};
      return {
        enabled: settings.enabled === true,
        cadence_preset: String(settings.cadence_preset || "daily"),
        channel_ids: Array.isArray(settings.channel_ids) ? settings.channel_ids.map((item) => String(item || "")) : [],
        quiet_no_change: settings.quiet_no_change === true,
        last_evaluated_at: String(settings.last_evaluated_at || ""),
        last_sent_at: String(settings.last_sent_at || ""),
        next_due_at: String(settings.next_due_at || ""),
        schedule_last_error: String(settings.schedule_last_error || ""),
        schedule_paused_reason: String(settings.schedule_paused_reason || ""),
        schedule_last_fire_at: String(settings.schedule_last_fire_at || ""),
        schedule_last_fire_reason: String(settings.schedule_last_fire_reason || ""),
        schedule_last_fire_status: String(settings.schedule_last_fire_status || "")
      };
    }
    function digestChannelLabel(channel) {
      const kind = String(channel?.kind || "").replaceAll("_", " ");
      const label = String(channel?.label || channel?.id || "Channel");
      return kind ? `${label} · ${kind}` : label;
    }
    function renderDigestSettings(projectId, st, { mobile = false } = {}) {
      const settings = digestSettingsOrDefault(st);
      const channels = Array.isArray(st.digestChannels) ? st.digestChannels : [];
      const selectedChannels = new Set(settings.channel_ids);
      const canManage = st.canManageDigestSettings !== false;
      const section = document.createElement("section");
      section.className = mobile ? "project-monitoring-digest is-mobile" : "project-monitoring-digest";
      section.dataset.projectDigestSettings = String(projectId || "");
      const head = document.createElement("div");
      head.className = "project-monitoring-digest-head";
      const title = document.createElement("div");
      title.className = "project-monitoring-digest-title";
      const heading = document.createElement("h3");
      heading.className = mobile ? "project-mobile-section-heading" : "project-explorer-section-heading";
      heading.textContent = "Digest Notifications";
      const status = document.createElement("span");
      status.className = settings.enabled ? "badge badge-tone-green project-monitoring-digest-status" : "badge badge-tone-muted project-monitoring-digest-status";
      status.textContent = settings.enabled ? "Enabled" : "Off";
      title.append(heading, status);
      const save = makeActionButton("Save", projectId, "primary");
      save.dataset.projectMonitoringAction = "save-digest";
      save.dataset.projectId = String(projectId || "");
      save.disabled = !canManage;
      if (!canManage) save.title = "View-only team members can't change digest settings";
      head.append(title, save);
      const controls = document.createElement("div");
      controls.className = "project-monitoring-digest-controls";
      const enabledLabel = document.createElement("label");
      enabledLabel.className = "form-check project-monitoring-digest-toggle";
      const enabled = document.createElement("input");
      enabled.type = "checkbox";
      enabled.checked = settings.enabled;
      enabled.disabled = !canManage;
      enabled.dataset.projectDigestField = "enabled";
      const enabledText = document.createElement("span");
      enabledText.textContent = "Send scheduled digests";
      enabledLabel.append(enabled, enabledText);
      const cadenceLabelWrap = document.createElement("label");
      cadenceLabelWrap.className = "project-monitoring-digest-field";
      const cadenceText = document.createElement("span");
      cadenceText.textContent = "Cadence";
      const cadence = document.createElement("select");
      cadence.className = "form-select";
      cadence.dataset.projectDigestField = "cadence_preset";
      cadence.disabled = !canManage;
      [
        ["hourly", "Hourly"],
        ["daily", "Daily"],
        ["weekly", "Weekly"]
      ].forEach(([value, label]) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = label;
        cadence.appendChild(option);
      });
      cadence.value = ["hourly", "daily", "weekly"].includes(settings.cadence_preset) ? settings.cadence_preset : "daily";
      cadenceLabelWrap.append(cadenceText, cadence);
      const quietLabel = document.createElement("label");
      quietLabel.className = "form-check project-monitoring-digest-toggle";
      const quiet = document.createElement("input");
      quiet.type = "checkbox";
      quiet.checked = settings.quiet_no_change;
      quiet.disabled = !canManage;
      quiet.dataset.projectDigestField = "quiet_no_change";
      const quietText = document.createElement("span");
      quietText.textContent = "Send quiet digests";
      quietLabel.append(quiet, quietText);
      controls.append(enabledLabel, cadenceLabelWrap, quietLabel);
      const channelWrap = document.createElement("div");
      channelWrap.className = "project-monitoring-digest-channels nice-scroll";
      const channelTitle = document.createElement("div");
      channelTitle.className = "project-monitoring-digest-label";
      channelTitle.textContent = "Channels";
      channelWrap.appendChild(channelTitle);
      if (!channels.length) {
        const empty = document.createElement("div");
        empty.className = "project-monitoring-empty-line project-monitoring-digest-empty";
        empty.textContent = "No notification channels are configured.";
        channelWrap.appendChild(empty);
      } else {
        channels.forEach((channel) => {
          const channelId = String(channel?.id || "");
          if (!channelId) return;
          const label = document.createElement("label");
          label.className = "form-check project-monitoring-digest-channel";
          const checkbox = document.createElement("input");
          checkbox.type = "checkbox";
          checkbox.value = channelId;
          checkbox.checked = selectedChannels.has(channelId);
          checkbox.disabled = !canManage;
          checkbox.dataset.projectDigestField = "channel";
          const text = document.createElement("span");
          text.textContent = digestChannelLabel(channel);
          label.append(checkbox, text);
          channelWrap.appendChild(label);
        });
      }
      const meta = document.createElement("div");
      meta.className = "project-monitoring-meta project-monitoring-digest-meta";
      meta.textContent = [
        settings.last_sent_at ? `last sent: ${formatDateLabel(settings.last_sent_at)}` : "",
        settings.next_due_at ? `next due: ${formatDateLabel(settings.next_due_at)}` : "",
        settings.last_evaluated_at ? `last checked: ${formatDateLabel(settings.last_evaluated_at)}` : "",
        settings.schedule_last_fire_reason ? `last result: ${settings.schedule_last_fire_reason}` : "",
        settings.schedule_paused_reason ? `paused: ${settings.schedule_paused_reason}` : "",
        settings.schedule_last_error ? `last issue: ${settings.schedule_last_error}` : "",
        canManage ? "" : "read-only"
      ].filter(Boolean).join(" · ");
      section.append(head, controls, channelWrap);
      if (meta.textContent) section.appendChild(meta);
      return section;
    }
    function makeActionButton(label, projectId, role = "secondary") {
      const normalizedRole = ["primary", "secondary", "ghost", "destructive"].includes(String(role || "")) ? String(role || "") : "secondary";
      if (typeof ctx.makeProjectButton === "function") {
        return ctx.makeProjectButton(label, "monitoring-action", projectId, normalizedRole);
      }
      if (typeof ctx.makeButton === "function") {
        return ctx.makeButton(label, "monitoring-action", projectId, normalizedRole);
      }
      throw new Error("Project Monitoring requires a shared project button factory.");
    }
    function statePill(state) {
      const normalized = String(state || "active");
      const pill = document.createElement("span");
      pill.className = `badge ${stateTone(normalized)} project-monitoring-pill is-${normalized}`;
      pill.textContent = labelForState(state);
      return pill;
    }
    function severityPill(severity) {
      const normalized = String(severity || "none");
      const pill = document.createElement("span");
      pill.className = `badge ${severityTone(normalized)} project-monitoring-severity is-${normalized}`;
      pill.textContent = labelForSeverity(normalized);
      return pill;
    }
    function ackPill(state) {
      const normalized = String(state || "new");
      const pill = document.createElement("span");
      pill.className = `badge ${ackTone(normalized)} project-monitoring-ack is-${normalized}`;
      pill.textContent = labelForAck(normalized);
      return pill;
    }
    function renderRollup(rollup) {
      if (!rollup || typeof rollup !== "object") return null;
      const wrap = document.createElement("div");
      wrap.className = "project-monitoring-rollup";
      const counts = document.createElement("span");
      counts.className = "project-monitoring-rollup-counts";
      counts.textContent = [
        Number(rollup.added || 0) ? `+${Number(rollup.added || 0)}` : "",
        Number(rollup.changed || 0) ? `~${Number(rollup.changed || 0)}` : "",
        Number(rollup.removed || 0) ? `-${Number(rollup.removed || 0)}` : ""
      ].filter(Boolean).join(" ");
      wrap.appendChild(severityPill(rollup.severity));
      if (counts.textContent) wrap.appendChild(counts);
      if (rollup.truncated) {
        const truncated = document.createElement("span");
        truncated.className = "badge badge-tone-amber project-monitoring-rollup-note";
        truncated.textContent = "truncated";
        wrap.appendChild(truncated);
      }
      const signals = Array.isArray(rollup.top_signals) ? rollup.top_signals.slice(0, 3) : [];
      if (signals.length) {
        const list = document.createElement("ul");
        list.className = "project-monitoring-signals";
        signals.forEach((signal) => {
          const item = document.createElement("li");
          item.textContent = String(signal && signal.label || "");
          if (item.textContent) list.appendChild(item);
        });
        if (list.childElementCount) wrap.appendChild(list);
      }
      return wrap;
    }
    function renderCounts(st) {
      const grid = document.createElement("div");
      grid.className = "project-monitoring-counts";
      countItems.forEach(([key, label]) => {
        const item = document.createElement("div");
        item.className = `project-monitoring-count is-${key}`;
        const value = document.createElement("strong");
        value.textContent = String(Number(st.counts?.[key] || 0));
        const text = document.createElement("span");
        text.textContent = label;
        item.append(value, text);
        grid.appendChild(item);
      });
      return grid;
    }
    function renderFilterSelect(projectId, key, label, options, st) {
      const wrap = document.createElement("label");
      wrap.className = "project-monitoring-filter";
      const text = document.createElement("span");
      text.textContent = label;
      const select = document.createElement("select");
      select.className = "form-select";
      select.dataset.projectMonitoringFilter = key;
      select.dataset.projectId = String(projectId || "");
      const all = document.createElement("option");
      all.value = "";
      all.textContent = "All";
      select.appendChild(all);
      (options || []).forEach((option) => {
        const item = document.createElement("option");
        item.value = String(option.value ?? option.id ?? option.key ?? "");
        item.textContent = String(option.label ?? option.value ?? option.id ?? "");
        select.appendChild(item);
      });
      select.value = filterValue(st, key);
      wrap.append(text, select);
      return wrap;
    }
    function renderFilters(projectId, st) {
      const filters = document.createElement("div");
      filters.className = "project-monitoring-filters";
      const opts = st.filterOptions || {};
      filters.append(
        renderFilterSelect(projectId, "status", "Status", opts.statuses || [], st),
        renderFilterSelect(projectId, "severity", "Severity", opts.severities || [], st),
        renderFilterSelect(projectId, "classifier", "Tool", opts.classifiers || [], st),
        renderFilterSelect(projectId, "group", "Group", opts.groups || [], st),
        renderFilterSelect(projectId, "cadence", "Cadence", opts.cadences || [], st),
        renderFilterSelect(projectId, "ack", "Ack", (opts.ack_states || []).map((item) => ({
          value: item.value,
          label: optionLabel("ack", item.value)
        })), st),
        renderFilterSelect(projectId, "changed_since", "Changed", [
          { value: "1", label: "24h" },
          { value: "7", label: "7d" },
          { value: "30", label: "30d" }
        ], st),
        renderFilterSelect(projectId, "target", "Target", (opts.targets || []).map((item) => ({
          value: item.value,
          label: item.value
        })), st)
      );
      const reset = makeActionButton("Reset", projectId, "ghost");
      reset.dataset.projectMonitoringAction = "reset-filters";
      reset.dataset.projectId = String(projectId || "");
      filters.appendChild(reset);
      return filters;
    }
    function makeRunButton(label, action, projectId, fire, runKey) {
      const run = fire && fire[runKey];
      const runId = String(run && run.id || "");
      const button = makeActionButton(label, projectId, runId ? "secondary" : "ghost");
      button.dataset.projectMonitoringAction = action;
      button.dataset.projectId = String(projectId || "");
      button.dataset.runId = runId;
      button.disabled = !runId;
      if (!runId) button.title = "Run is no longer available";
      return button;
    }
    function makeCompareButton(projectId, fire) {
      const runId = String(fire?.run?.id || "");
      const baselineId = String(fire?.baseline_run?.id || "");
      const button = makeActionButton("Compare", projectId, runId && baselineId ? "secondary" : "ghost");
      button.dataset.projectMonitoringAction = "compare";
      button.dataset.projectId = String(projectId || "");
      button.dataset.runId = runId;
      button.dataset.baselineRunId = baselineId;
      button.disabled = !runId || !baselineId || runId === baselineId;
      if (button.disabled) button.title = "Comparison is unavailable";
      return button;
    }
    function makeMonitorButton(label, action, projectId, watcherId, role = "secondary") {
      const button = makeActionButton(label, projectId, role);
      button.dataset.projectMonitoringAction = action;
      button.dataset.projectId = String(projectId || "");
      button.dataset.watcherId = String(watcherId || "");
      button.disabled = !String(watcherId || "");
      return button;
    }
    function makeAckButton(label, ackState, projectId, fireId, role = "secondary") {
      const button = makeActionButton(label, projectId, role);
      button.dataset.projectMonitoringAction = "ack";
      button.dataset.projectId = String(projectId || "");
      button.dataset.fireId = String(fireId || "");
      button.dataset.ackState = String(ackState || "new");
      button.disabled = !String(fireId || "");
      return button;
    }
    function isActionableFire(fire) {
      return ["changed", "failed"].includes(String(fire?.fire_kind || ""));
    }
    function renderAckControls(projectId, fire) {
      const wrap = document.createElement("div");
      wrap.className = "project-monitoring-triage";
      const note = document.createElement("textarea");
      note.className = "project-monitoring-note";
      note.rows = 2;
      note.value = String(fire.ack_note || "");
      note.placeholder = "Note";
      note.dataset.projectMonitoringNote = String(fire.id || "");
      const buttons = document.createElement("div");
      buttons.className = "project-monitoring-triage-actions";
      buttons.append(
        makeAckButton("Acknowledge", "acknowledged", projectId, fire.id),
        makeAckButton("Needs action", "needs_action", projectId, fire.id),
        makeAckButton("Expected", "expected", projectId, fire.id),
        makeAckButton("Resolved", "resolved", projectId, fire.id)
      );
      wrap.append(note, buttons);
      return wrap;
    }
    function renderFire(projectId, fire, { mobile = false, triage = true } = {}) {
      const row = document.createElement("div");
      row.className = mobile ? "project-monitoring-timeline-row is-mobile" : "project-monitoring-timeline-row";
      const main = document.createElement("div");
      main.className = "project-monitoring-timeline-main";
      const heading = document.createElement("div");
      heading.className = "project-monitoring-timeline-heading";
      row.dataset.projectMonitoringFireId = String(fire.id || "");
      const kind = document.createElement("span");
      const normalizedKind = String(fire.fire_kind || "unclassified");
      kind.className = `badge ${fireKindTone(normalizedKind)} project-monitoring-fire-kind is-${normalizedKind}`;
      kind.textContent = labelForFireKind(fire.fire_kind);
      const title = document.createElement("strong");
      title.textContent = String(fire.watcher_label || fire.watcher_command || "Monitor");
      heading.append(kind, title, ackPill(fire.ack_state));
      if (fire.rollup) heading.appendChild(severityPill(fire.rollup.severity));
      appendMeta(main, [
        ctx.formatDate ? ctx.formatDate(fire.created) : fire.created,
        runLabel(fire.run, String(fire.run_id || ""))
      ]);
      main.prepend(heading);
      const rollup = renderRollup(fire.rollup);
      if (rollup) main.appendChild(rollup);
      const actions = document.createElement("div");
      actions.className = "project-monitoring-actions";
      actions.append(
        makeRunButton("Details", "details", projectId, fire, "run"),
        makeCompareButton(projectId, fire)
      );
      if (triage && isActionableFire(fire)) main.appendChild(renderAckControls(projectId, fire));
      row.append(main, actions);
      return row;
    }
    function renderMonitor(projectId, monitor, { mobile = false } = {}) {
      const card = document.createElement("div");
      card.className = mobile ? "project-monitoring-card is-mobile" : "project-monitoring-card";
      const head = document.createElement("div");
      head.className = "project-monitoring-card-head";
      const title = document.createElement("strong");
      title.textContent = String(monitor.label || monitor.command_text || "Monitor");
      head.append(title, statePill(monitor.dashboard_state));
      const command = document.createElement("div");
      command.className = "project-monitoring-command";
      command.textContent = String(monitor.command_text || "");
      const monitorActions = document.createElement("div");
      monitorActions.className = "project-monitoring-card-actions";
      const pauseAction = monitor.dashboard_state === "paused" || monitor.state === "paused" ? "resume" : "pause";
      monitorActions.append(
        makeMonitorButton("Run now", "run-now", projectId, monitor.id),
        makeMonitorButton(pauseAction === "resume" ? "Resume" : "Pause", pauseAction, projectId, monitor.id),
        makeMonitorButton("Settings", "settings", projectId, monitor.id)
      );
      if (monitor.latest_fire?.run?.id) {
        const accept = makeMonitorButton("Accept baseline", "accept-baseline", projectId, monitor.id);
        accept.dataset.runId = String(monitor.latest_fire.run.id || "");
        monitorActions.appendChild(accept);
      }
      appendMeta(card, [
        cadenceLabel(monitor.schedule),
        monitor.schedule?.next_run_at ? `next run: ${formatDateLabel(monitor.schedule.next_run_at)}` : "",
        runMetaLabel("last run", monitor.last_run, monitor.last_run_id),
        lastChangeDate(monitor) ? `last change: ${formatDateLabel(lastChangeDate(monitor))}` : "",
        runMetaLabel("current baseline", monitor.baseline_run, monitor.baseline_run_id),
        monitor.monitor_group?.label || "",
        itemTargetValues(monitor).join(", "),
        monitor.schedule?.enabled === false ? "paused schedule" : "",
        monitor.last_error ? `last error: ${monitor.last_error}` : "",
        monitor.current_triage_state ? `triage: ${labelForAck(monitor.current_triage_state)}` : ""
      ]);
      card.prepend(head, command, monitorActions);
      const policy = document.createElement("div");
      policy.className = "project-monitoring-policy";
      const options = monitor.options || {};
      const monitorPolicy = monitor.policy && typeof monitor.policy === "object" ? monitor.policy : {};
      const patterns = Array.isArray(monitorPolicy.ignore_line_patterns) ? monitorPolicy.ignore_line_patterns : [];
      const signalClasses = Array.isArray(monitorPolicy.alert_signal_classes) ? monitorPolicy.alert_signal_classes : [];
      const repeated = Math.max(1, Number(monitorPolicy.alert_after_repeated_changes || 1) || 1);
      const labels = [
        options.suppress_removals ? "Ignoring removals" : "Tracking removals",
        options.notify_metadata_changes ? "Metadata alerts on" : "Metadata alerts off",
        repeated > 1 ? `Alerts after ${repeated} changes` : "First change alerts",
        patterns.length ? `Ignoring ${patterns.length} patterns` : "",
        signalClasses.length ? `Signals: ${signalClasses.join(", ")}` : "All signals"
      ].filter(Boolean);
      labels.forEach((label) => {
        const chip = document.createElement("span");
        chip.className = "badge badge-tone-muted project-monitoring-policy-chip";
        chip.textContent = label;
        policy.appendChild(chip);
      });
      card.appendChild(policy);
      const latest = monitor.latest_fire;
      if (latest) card.appendChild(renderFire(projectId, latest, { mobile, triage: false }));
      else {
        const empty = document.createElement("div");
        empty.className = "project-monitoring-empty-line";
        empty.textContent = "No checks have run yet.";
        card.appendChild(empty);
      }
      return card;
    }
    function renderTimeline(projectId, st, { mobile = false } = {}) {
      const section = document.createElement("section");
      section.className = "project-monitoring-section";
      const heading = document.createElement("h3");
      heading.className = mobile ? "project-mobile-section-heading" : "project-explorer-section-heading";
      heading.textContent = "Timeline";
      const list = document.createElement("div");
      list.className = mobile ? "project-monitoring-timeline nice-scroll is-mobile" : "project-monitoring-timeline nice-scroll";
      const filteredTimeline = st.timeline.filter((fire) => matchesFire(fire, st.filters || {}));
      if (!filteredTimeline.length) {
        const empty = document.createElement("div");
        empty.className = "project-monitoring-empty-line";
        empty.textContent = "No monitoring events yet.";
        list.appendChild(empty);
      } else {
        filteredTimeline.forEach((fire) => list.appendChild(renderFire(projectId, fire, { mobile })));
      }
      section.append(heading, list);
      return section;
    }
    function renderLoaded(projectId, st, { mobile = false } = {}) {
      const root = document.createElement("div");
      root.className = mobile ? "project-monitoring-root is-mobile" : "project-monitoring-root";
      root.dataset.projectMonitoringRoot = String(projectId || "");
      root.appendChild(renderCounts(st));
      root.appendChild(renderFilters(projectId, st));
      root.appendChild(renderDigestSettings(projectId, st, { mobile }));
      const monitors = document.createElement("section");
      monitors.className = "project-monitoring-section";
      const heading = document.createElement("h3");
      heading.className = mobile ? "project-mobile-section-heading" : "project-explorer-section-heading";
      const headingText = document.createElement("span");
      headingText.textContent = "Monitors";
      const newMonitor = makeActionButton("New monitor", projectId, "primary");
      newMonitor.dataset.projectMonitoringAction = "new-monitor";
      newMonitor.dataset.projectId = String(projectId || "");
      heading.append(headingText, newMonitor);
      const list = document.createElement("div");
      list.className = "project-monitoring-grid";
      const filteredMonitors = st.monitors.filter((monitor) => matchesMonitor(monitor, st.filters || {}));
      if (!filteredMonitors.length) {
        const empty = document.createElement("div");
        empty.className = "project-monitoring-empty-line";
        empty.textContent = "No monitors are linked to this project.";
        list.appendChild(empty);
      } else {
        const groups = /* @__PURE__ */ new Map();
        filteredMonitors.forEach((monitor) => {
          const key = String(monitor.monitor_group?.key || "custom");
          if (!groups.has(key)) groups.set(key, []);
          groups.get(key).push(monitor);
        });
        groups.forEach((items) => {
          const group = document.createElement("section");
          group.className = "project-monitoring-group";
          const groupHeading = document.createElement("h4");
          groupHeading.className = "project-monitoring-group-heading";
          groupHeading.textContent = String(items[0]?.monitor_group?.label || "Custom commands");
          const groupList = document.createElement("div");
          groupList.className = "project-monitoring-grid project-monitoring-card-grid";
          items.forEach((monitor) => groupList.appendChild(renderMonitor(projectId, monitor, { mobile })));
          group.append(groupHeading, groupList);
          list.appendChild(group);
        });
      }
      monitors.append(heading, list);
      root.append(monitors, renderTimeline(projectId, st, { mobile }));
      return root;
    }
    function renderFallback(projectId, text, retry = false) {
      const panel = ctx.emptyProjectPanel ? ctx.emptyProjectPanel(text) : document.createElement("div");
      if (!ctx.emptyProjectPanel) panel.textContent = text;
      if (retry) {
        const button = makeActionButton("Retry", projectId, "secondary");
        button.dataset.projectMonitoringAction = "retry";
        button.dataset.projectId = String(projectId || "");
        panel.appendChild(button);
      }
      return panel;
    }
    function renderMonitoring(container, projectId) {
      const st = stateFor(projectId);
      if (!st.loaded && !st.loading && !st.error) {
        void load(projectId, { render: true });
      }
      if (st.loading && !st.loaded) {
        container.replaceChildren(renderFallback(projectId, "Loading project monitoring..."));
        return;
      }
      if (st.error) {
        container.replaceChildren(renderFallback(projectId, st.error, true));
        return;
      }
      container.replaceChildren(renderLoaded(projectId, st));
    }
    function renderMobileMonitoringTab(projectId) {
      const st = stateFor(projectId);
      if (!st.loaded && !st.loading && !st.error) {
        void load(projectId, { render: true });
      }
      if (st.loading && !st.loaded) return renderFallback(projectId, "Loading project monitoring...");
      if (st.error) return renderFallback(projectId, st.error, true);
      return renderLoaded(projectId, st, { mobile: true });
    }
    async function openRunDetails(runId) {
      const normalizedRunId = String(runId || "").trim();
      if (!normalizedRunId) return false;
      const hasImportedHandler = typeof hasHistoryRunModalStateHandler === "function" && hasHistoryRunModalStateHandler("openHistoryRunDetails");
      const openDetails = hasImportedHandler && typeof openHistoryRunDetails === "function" ? openHistoryRunDetails : typeof global.openHistoryRunDetails === "function" ? global.openHistoryRunDetails : null;
      if (typeof openDetails !== "function") return false;
      try {
        const result = await openDetails({ id: normalizedRunId });
        return result !== false;
      } catch (err) {
        ctx.logClientError?.("project monitoring run details unavailable", err);
        return false;
      }
    }
    async function compareRuns(projectId, runId, baselineRunId) {
      const left = String(runId || "").trim();
      const right = String(baselineRunId || "").trim();
      if (!left || !right || left === right) return false;
      const hasImportedHandler = typeof hasHistoryCompareHandler === "function" && hasHistoryCompareHandler("fetchAndRenderHistoryComparison");
      const compareFn = hasImportedHandler && typeof fetchAndRenderHistoryComparison === "function" ? fetchAndRenderHistoryComparison : typeof global.fetchAndRenderHistoryComparison === "function" ? global.fetchAndRenderHistoryComparison : null;
      if (typeof compareFn !== "function") return false;
      const params = new URLSearchParams({
        left,
        right,
        project_id: String(projectId || "")
      });
      try {
        const result = await compareFn(left, right, { url: `/history/compare?${params.toString()}` });
        return result !== false;
      } catch (err) {
        ctx.logClientError?.("project monitoring run comparison unavailable", err);
        return false;
      }
    }
    async function monitoringRequest(url, options = {}) {
      const resp = await ctx.projectWorkspaceRequest(url, {
        ...options,
        headers: {
          ...options.headers || {},
          ...options.body ? { "Content-Type": "application/json" } : {}
        }
      });
      if (!resp.ok) throw await responseError(resp, "Monitoring action failed.");
      return resp;
    }
    async function reloadAfterAction(projectId, message) {
      if (message) ctx.setProjectWorkspaceMessage?.(message);
      await load(projectId, { force: true });
    }
    async function updateWatcher(projectId, watcherId, payload, message) {
      await monitoringRequest(`/watchers/${encodeURIComponent(watcherId)}`, {
        method: "PATCH",
        body: JSON.stringify(payload)
      });
      await reloadAfterAction(projectId, message);
    }
    async function runWatcherNow(projectId, watcherId) {
      await monitoringRequest(`/watchers/${encodeURIComponent(watcherId)}/run-now`, { method: "POST" });
      await reloadAfterAction(projectId, "Monitor queued.");
    }
    async function confirmAcceptBaseline() {
      const confirm = typeof ctx.showConfirm === "function" ? ctx.showConfirm : typeof global.showConfirm === "function" ? global.showConfirm : null;
      if (typeof confirm !== "function") return true;
      const choice = await confirm({
        body: "Accept the latest watcher run as the new baseline?",
        tone: "warning",
        actions: [
          { id: "cancel", label: "Cancel", role: "cancel" },
          { id: "accept", label: "Accept baseline", role: "primary" }
        ]
      });
      return choice === "accept";
    }
    async function acceptBaseline(projectId, watcherId, runId) {
      if (!await confirmAcceptBaseline()) return;
      await monitoringRequest(`/watchers/${encodeURIComponent(watcherId)}/accept-baseline`, {
        method: "POST",
        body: JSON.stringify({ run_id: String(runId || "") })
      });
      await reloadAfterAction(projectId, "Baseline accepted.");
    }
    async function openWatcherSettings(watcherId) {
      const open = typeof global.openWatchersModal === "function" ? global.openWatchersModal : typeof globalThis.openWatchersModal === "function" ? globalThis.openWatchersModal : null;
      if (!open) return false;
      await open({ watcherId: String(watcherId || "") });
      return true;
    }
    async function openNewMonitor(projectId) {
      const open = typeof global.openWatchersModal === "function" ? global.openWatchersModal : typeof globalThis.openWatchersModal === "function" ? globalThis.openWatchersModal : null;
      if (!open) return false;
      await open({ projectId: String(projectId || ""), newWatcher: true });
      return true;
    }
    async function updateAck(projectId, fireId, ackState, note) {
      await monitoringRequest(
        `/projects/${encodeURIComponent(projectId)}/monitoring/fires/${encodeURIComponent(fireId)}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            ack_state: String(ackState || "new"),
            ack_note: String(note || "")
          })
        }
      );
      await reloadAfterAction(projectId, "Monitoring event updated.");
    }
    function digestPayloadFromRoot(root) {
      const selectedChannels = [...root?.querySelectorAll?.('[data-project-digest-field="channel"]:checked') || []].map((item) => String(item.value || "")).filter(Boolean);
      return {
        enabled: !!root?.querySelector?.('[data-project-digest-field="enabled"]')?.checked,
        cadence_preset: String(root?.querySelector?.('[data-project-digest-field="cadence_preset"]')?.value || "daily"),
        channel_ids: selectedChannels,
        quiet_no_change: !!root?.querySelector?.('[data-project-digest-field="quiet_no_change"]')?.checked
      };
    }
    async function saveDigestSettings(projectId, action) {
      const root = action.closest("[data-project-digest-settings]");
      const payload = digestPayloadFromRoot(root);
      const resp = await monitoringRequest(`/projects/${encodeURIComponent(projectId)}/digest-settings`, {
        method: "PATCH",
        body: JSON.stringify(payload)
      });
      const data = await resp.json();
      const st = stateFor(projectId);
      st.digestSettings = data && typeof data.digest_settings === "object" ? data.digest_settings : st.digestSettings;
      st.digestChannels = Array.isArray(data?.notification_channels) ? data.notification_channels : st.digestChannels;
      st.canManageDigestSettings = data?.can_manage_digest_settings !== false;
      ctx.setProjectWorkspaceMessage?.("Digest settings saved.");
      ctx.renderProjectExplorer?.();
      if (ctx.mobileView?.() === "detail") ctx.renderProjectMobileDetail?.();
    }
    async function handleClick(event) {
      const action = event.target.closest?.("[data-project-monitoring-action]");
      if (!action) return false;
      event.preventDefault();
      event.stopPropagation();
      const projectId = String(action.dataset.projectId || action.closest("[data-project-monitoring-root]")?.dataset.projectMonitoringRoot || "");
      const name = String(action.dataset.projectMonitoringAction || "");
      if (name === "retry") {
        await load(projectId, { force: true });
        return true;
      }
      if (name === "reset-filters") {
        stateFor(projectId).filters = {};
        ctx.renderProjectExplorer?.();
        if (ctx.mobileView?.() === "detail") ctx.renderProjectMobileDetail?.();
        return true;
      }
      if (name === "details") {
        if (!await openRunDetails(action.dataset.runId)) {
          ctx.setProjectWorkspaceMessage?.("Run details are unavailable.", { error: true });
        }
        return true;
      }
      if (name === "compare") {
        if (!await compareRuns(projectId, action.dataset.runId, action.dataset.baselineRunId)) {
          ctx.setProjectWorkspaceMessage?.("Run comparison is unavailable.", { error: true });
        }
        return true;
      }
      try {
        if (name === "save-digest") {
          await saveDigestSettings(projectId, action);
          return true;
        }
        if (name === "pause") {
          await updateWatcher(projectId, action.dataset.watcherId, { pause: true, reason: "operator paused" }, "Monitor paused.");
          return true;
        }
        if (name === "resume") {
          await updateWatcher(projectId, action.dataset.watcherId, { resume: true }, "Monitor resumed.");
          return true;
        }
        if (name === "run-now") {
          await runWatcherNow(projectId, action.dataset.watcherId);
          return true;
        }
        if (name === "accept-baseline") {
          await acceptBaseline(projectId, action.dataset.watcherId, action.dataset.runId);
          return true;
        }
        if (name === "settings") {
          if (!await openWatcherSettings(action.dataset.watcherId)) {
            ctx.setProjectWorkspaceMessage?.("Watcher settings are unavailable.", { error: true });
          }
          return true;
        }
        if (name === "new-monitor") {
          if (!await openNewMonitor(projectId)) {
            ctx.setProjectWorkspaceMessage?.("Watcher settings are unavailable.", { error: true });
          }
          return true;
        }
        if (name === "ack") {
          const row = action.closest("[data-project-monitoring-fire-id]");
          const note = [...row?.querySelectorAll?.("[data-project-monitoring-note]") || []].find((item) => item.dataset.projectMonitoringNote === String(action.dataset.fireId || ""))?.value || "";
          await updateAck(projectId, action.dataset.fireId, action.dataset.ackState, note);
          return true;
        }
      } catch (err) {
        logClientEvent("PROJECT_MONITORING_CLIENT_ACTION_FAILED", err, {
          phase: name || "unknown",
          selection_key: `project:${projectId}`,
          watcher_id: String(action.dataset.watcherId || ""),
          fire_id: String(action.dataset.fireId || ""),
          ack_state: String(action.dataset.ackState || ""),
          note_chars: name === "ack" ? (action.closest("[data-project-monitoring-fire-id]")?.querySelector("[data-project-monitoring-note]")?.value || "").length : 0
        });
        ctx.setProjectWorkspaceMessage?.(err && err.message ? err.message : "Monitoring action failed.", { error: true });
        return true;
      }
      return false;
    }
    function handleChange(event) {
      const control = event.target.closest?.("[data-project-monitoring-filter]");
      if (!control) return false;
      event.preventDefault();
      event.stopPropagation();
      const projectId = String(control.dataset.projectId || control.closest("[data-project-monitoring-root]")?.dataset.projectMonitoringRoot || "");
      const key = String(control.dataset.projectMonitoringFilter || "");
      if (!projectId || !key) return false;
      const st = stateFor(projectId);
      st.filters = { ...st.filters || {}, [key]: String(control.value || "") };
      if (!st.filters[key]) delete st.filters[key];
      ctx.renderProjectExplorer?.();
      if (ctx.mobileView?.() === "detail") ctx.renderProjectMobileDetail?.();
      return true;
    }
    return {
      handleChange,
      handleClick,
      invalidate,
      load,
      renderMobileMonitoringTab,
      renderMonitoring,
      stateFor
    };
  }
  const DarklabProjectMonitoring = { createProjectMonitoringController };
  exportedDarklabProjectMonitoring = DarklabProjectMonitoring;
})(globalThis);
export {
  exportedDarklabProjectMonitoring as DarklabProjectMonitoring
};
