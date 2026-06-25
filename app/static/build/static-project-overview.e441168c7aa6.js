// app/static/js/features/projects/project_overview.js
var exportedDarklabProjectOverview = null;
(function projectOverviewModule(global) {
  "use strict";
  const certificateLabels = {
    expired: "Expired",
    expiring_14d: "<=14d",
    expiring_30d: "<=30d",
    healthy: "Healthy",
    unknown: "Unknown"
  };
  const severityLabels = {
    critical: "Critical",
    high: "High",
    medium: "Medium",
    low: "Low",
    info: "Info"
  };
  const recentLabels = {
    windowed: "Windowed",
    "watcher-context-only": "Watcher context",
    "not-monitored": "Not monitored"
  };
  function createProjectOverviewController(context) {
    const ctx = context || {};
    const states = /* @__PURE__ */ new Map();
    function defaultState() {
      return {
        error: "",
        loaded: false,
        loading: false,
        payload: null
      };
    }
    function stateFor(projectId) {
      const normalized = String(projectId || "");
      if (!states.has(normalized)) states.set(normalized, defaultState());
      return states.get(normalized);
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
      ctx.logClientError(`${eventName} ${JSON.stringify({ page: "project_overview", ...details })}`, err);
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
          `/projects/${encodeURIComponent(normalized)}/overview`,
          { cache: "no-store" }
        );
        if (!resp.ok) throw await responseError(resp, "Could not load project overview.");
        const payload = await resp.json();
        st.payload = payload && typeof payload === "object" ? payload : {};
        st.loaded = true;
      } catch (err) {
        st.error = err && err.message ? err.message : "Could not load project overview.";
        logClientEvent("PROJECT_OVERVIEW_CLIENT_LOAD_FAILED", err, {
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
    function targets(st) {
      const payload = st && st.payload && typeof st.payload === "object" ? st.payload : {};
      return Array.isArray(payload.targets) ? payload.targets : [];
    }
    function rollups(st) {
      const payload = st && st.payload && typeof st.payload === "object" ? st.payload : {};
      return payload.rollups && typeof payload.rollups === "object" ? payload.rollups : {};
    }
    function formatCount(value) {
      const count = Number(value || 0);
      return Number.isFinite(count) ? count.toLocaleString() : "0";
    }
    function formatDate(value) {
      const normalized = String(value || "");
      if (!normalized) return "";
      return typeof ctx.formatDate === "function" ? ctx.formatDate(normalized) : normalized;
    }
    function readableToken(value) {
      return String(value || "").replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
    }
    function certificateTone(status) {
      const normalized = String(status || "unknown");
      if (normalized === "expired") return "badge-tone-red";
      if (normalized === "expiring_14d" || normalized === "expiring_30d") return "badge-tone-amber";
      if (normalized === "healthy") return "badge-tone-green";
      return "badge-tone-muted";
    }
    function severityTone(severity) {
      const normalized = String(severity || "");
      if (normalized === "critical") return "badge-tone-red";
      if (normalized === "high" || normalized === "medium") return "badge-tone-amber";
      if (normalized === "low" || normalized === "info") return "badge-tone-muted";
      return "badge-tone-muted";
    }
    function recentTone(state) {
      const normalized = String(state || "not-monitored");
      if (normalized === "windowed") return "badge-tone-green";
      if (normalized === "watcher-context-only") return "badge-tone-cyan";
      return "badge-tone-muted";
    }
    function badge(label, tone = "badge-tone-muted", className = "", title = "") {
      const item = document.createElement("span");
      item.className = `badge ${tone}${className ? ` ${className}` : ""}`;
      item.textContent = String(label || "");
      if (title) item.title = title;
      return item;
    }
    function summaryCard(label, value, detail = "", tone = "") {
      const card = document.createElement("div");
      card.className = `project-overview-summary-card${tone ? ` is-${tone}` : ""}`;
      const strong = document.createElement("strong");
      strong.textContent = String(value || "0");
      const span = document.createElement("span");
      span.textContent = label;
      card.append(strong, span);
      if (detail) {
        const meta = document.createElement("div");
        meta.className = "project-overview-summary-detail";
        meta.textContent = detail;
        card.appendChild(meta);
      }
      return card;
    }
    function renderRollups(st) {
      const source = rollups(st);
      const certs = source.certificate_statuses && typeof source.certificate_statuses === "object" ? source.certificate_statuses : {};
      const severities = source.finding_severities && typeof source.finding_severities === "object" ? source.finding_severities : {};
      const highSignal = Number(severities.critical || 0) + Number(severities.high || 0);
      const certAttention = Number(certs.expired || 0) + Number(certs.expiring_14d || 0) + Number(certs.expiring_30d || 0);
      const recentState = String(source.recent_change_state || "not-monitored");
      const grid = document.createElement("div");
      grid.className = "project-overview-summary-grid";
      grid.append(
        summaryCard("Targets", formatCount(source.target_count), `${formatCount(source.provider_count)} providers`),
        summaryCard("Ports", formatCount(source.open_port_count), `${formatCount(source.service_count)} services`),
        summaryCard("Finding signal", formatCount(highSignal), "critical/high", highSignal ? "attention" : ""),
        summaryCard("Certificates", formatCount(certAttention), "expired or expiring", certAttention ? "attention" : ""),
        summaryCard("Recent changes", recentLabels[recentState] || readableToken(recentState), "", recentState)
      );
      return grid;
    }
    function certificateText(certificate) {
      const source = certificate && typeof certificate === "object" ? certificate : {};
      const status = String(source.status || "unknown");
      const label = certificateLabels[status] || readableToken(status) || "Unknown";
      const days = source.days_until_expiry;
      if (status === "unknown") return label;
      if (Number.isFinite(Number(days))) {
        const count = Number(days);
        if (count < 0) return `${label} · ${Math.abs(count)}d ago`;
        return `${label} · ${count}d`;
      }
      return source.expires_at ? `${label} · ${formatDate(source.expires_at)}` : label;
    }
    function targetTitle(target) {
      return String(target?.value || target?.display_label || target?.entity_id || "Target");
    }
    function targetMeta(target) {
      return [
        String(target?.type || "target"),
        String(target?.target_review_state || "")
      ].filter(Boolean).join(" · ");
    }
    function providerHighlights(target) {
      const summary = target?.intel_summary && typeof target.intel_summary === "object" ? target.intel_summary : {};
      const highlights = Array.isArray(summary.highlights) ? summary.highlights : [];
      return highlights.map((item) => String(item?.label || item || "").trim()).filter(Boolean).slice(0, 3);
    }
    function portServiceText(target) {
      const ports = Array.isArray(target?.open_ports) ? target.open_ports : [];
      const services = Array.isArray(target?.services) ? target.services : [];
      const portText = ports.length ? ports.slice(0, 5).join(", ") : "No ports";
      const serviceText = services.length ? services.slice(0, 4).join(", ") : "No services";
      return `${portText} · ${serviceText}`;
    }
    function applyEntityHints(projectId, hints) {
      const targetId = String(hints?.target_id || "").trim();
      const runId = String(hints?.run_id || "").trim();
      const targetSet = ctx.projectTargetFilterSet?.(projectId);
      if (targetSet) {
        targetSet.clear();
        if (targetId) targetSet.add(targetId);
      }
      const runSet = ctx.projectRunFilterSet?.(projectId);
      if (runSet) {
        runSet.clear();
        if (runId) runSet.add(runId);
      }
    }
    function applyFindingHints(projectId, hints) {
      applyEntityHints(projectId, hints);
      const severity = String(hints?.severity || "").trim().toLowerCase();
      const severitySet = ctx.projectFindingSeverityFilterSet?.(projectId);
      if (severitySet) {
        severitySet.clear();
        if (severity) severitySet.add(severity);
      }
      const status = String(hints?.review_state || "").trim().toLowerCase();
      const statusSet = ctx.projectFindingStatusFilterSet?.(projectId);
      if (statusSet) {
        statusSet.clear();
        if (status) statusSet.add(status);
      }
      if (typeof ctx.setProjectFindingOrphanFilter === "function") {
        ctx.setProjectFindingOrphanFilter(projectId, String(hints?.orphan_filter || "hide"));
      }
      ctx.invalidateProjectFilteredFindings?.(projectId);
    }
    function gotoTab(projectId, tab, hints) {
      if (tab === "findings") applyFindingHints(projectId, hints || {});
      else if (tab === "entities") applyEntityHints(projectId, hints || {});
      ctx.setProjectWorkspaceTab?.(tab);
      if (ctx.mobileView?.() === "detail") ctx.renderProjectMobileDetail?.();
      else ctx.renderProjectExplorer?.();
    }
    function makeTabButton(projectId, label, tab, hints, role = "secondary") {
      const button = typeof ctx.makeProjectButton === "function" ? ctx.makeProjectButton(label, "overview-open", projectId, role) : document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.dataset.projectOverviewAction = tab;
      button.addEventListener("click", (event) => {
        event.preventDefault();
        gotoTab(projectId, tab, hints);
      });
      ctx.bindProjectRuntimePressable?.(button);
      return button;
    }
    function targetChips(target) {
      const chips = [];
      const severity = String(target?.top_finding_severity || "");
      if (severity) {
        const label = severityLabels[severity] || readableToken(severity);
        chips.push(badge(
          `Finding: ${label}`,
          severityTone(severity),
          "project-overview-chip",
          "Highest actionable finding severity for this target"
        ));
      }
      const certStatus = String(target?.certificate?.status || "unknown");
      chips.push(badge(
        `Cert: ${certificateText(target?.certificate)}`,
        certificateTone(certStatus),
        "project-overview-chip",
        certStatus === "unknown" ? "No usable certificate expiry data found for this target" : "Certificate expiry status for this target"
      ));
      if (target?.source_flags?.has_recent_changes) {
        chips.push(badge("Changed", "badge-tone-cyan", "project-overview-chip"));
      }
      if (!target?.source_flags?.has_intel) {
        chips.push(badge(
          "Intel: None",
          "badge-tone-muted",
          "project-overview-chip",
          "No cached provider data for this target"
        ));
      }
      return chips;
    }
    function renderTargetRow(projectId, target, { mobile = false } = {}) {
      const row = document.createElement("article");
      row.className = mobile ? "project-overview-target-row is-mobile" : "project-overview-target-row panel-row";
      const main = document.createElement("div");
      main.className = "project-overview-target-main";
      const title = document.createElement("div");
      title.className = "project-overview-target-title";
      title.textContent = targetTitle(target);
      const meta = document.createElement("div");
      meta.className = "project-overview-target-meta";
      meta.textContent = targetMeta(target);
      const detail = document.createElement("div");
      detail.className = "project-overview-target-detail";
      detail.textContent = portServiceText(target);
      const chipWrap = document.createElement("div");
      chipWrap.className = "project-overview-target-chips";
      targetChips(target).forEach((chip) => chipWrap.appendChild(chip));
      main.append(title, meta, detail, chipWrap);
      const highlights = providerHighlights(target);
      if (highlights.length) {
        const list = document.createElement("ul");
        list.className = "project-overview-highlights";
        highlights.forEach((highlight) => {
          const item = document.createElement("li");
          item.textContent = highlight;
          list.appendChild(item);
        });
        main.appendChild(list);
      }
      const actions = document.createElement("div");
      actions.className = "project-overview-target-actions";
      const hints = target?.deep_link_hints && typeof target.deep_link_hints === "object" ? target.deep_link_hints : {};
      actions.append(
        makeTabButton(projectId, "Entities", "entities", hints.entities || {}, "ghost"),
        makeTabButton(projectId, "Findings", "findings", hints.findings || {}, target?.top_finding_severity ? "secondary" : "ghost")
      );
      row.append(main, actions);
      return row;
    }
    function renderRecentState(st) {
      const source = rollups(st);
      const state = String(source.recent_change_state || "not-monitored");
      const wrap = document.createElement("div");
      wrap.className = "project-overview-recent-state";
      wrap.appendChild(badge(recentLabels[state] || readableToken(state), recentTone(state)));
      const changes = Array.isArray(st?.payload?.recent_changes) ? st.payload.recent_changes : [];
      if (!changes.length) {
        const text2 = document.createElement("span");
        text2.textContent = state === "not-monitored" ? "No monitoring window" : "No recent target changes";
        wrap.appendChild(text2);
        return wrap;
      }
      const text = document.createElement("span");
      text.textContent = `${changes.length} recent target change${changes.length === 1 ? "" : "s"}`;
      wrap.appendChild(text);
      return wrap;
    }
    function renderOverview(container, projectId, _summary, { mobile = false } = {}) {
      const normalized = String(projectId || "");
      const st = stateFor(normalized);
      if (!st.loaded && !st.loading) load(normalized).catch(() => {
      });
      if (st.loading && !st.loaded) {
        container.replaceChildren(ctx.emptyProjectPanel?.("Loading project overview...") || document.createTextNode("Loading project overview..."));
        return;
      }
      if (st.error && !st.loaded) {
        container.replaceChildren(ctx.emptyProjectPanel?.(st.error) || document.createTextNode(st.error));
        return;
      }
      const root = document.createElement("div");
      root.className = mobile ? "project-overview-root is-mobile" : "project-overview-root";
      root.dataset.projectOverviewRoot = normalized;
      root.appendChild(renderRollups(st));
      root.appendChild(renderRecentState(st));
      const rows = targets(st);
      if (!rows.length) {
        root.appendChild(ctx.emptyProjectPanel?.("No project targets yet.") || document.createTextNode("No project targets yet."));
        container.replaceChildren(root);
        return;
      }
      const list = document.createElement("div");
      list.className = "project-overview-target-list";
      rows.forEach((target) => list.appendChild(renderTargetRow(normalized, target, { mobile })));
      root.appendChild(list);
      container.replaceChildren(root);
    }
    function renderMobileOverviewTab(projectId, summary) {
      const panel = document.createElement("div");
      renderOverview(panel, projectId, summary, { mobile: true });
      return panel;
    }
    return {
      invalidate,
      load,
      renderMobileOverviewTab,
      renderOverview,
      stateFor
    };
  }
  const DarklabProjectOverview = {
    createProjectOverviewController
  };
  exportedDarklabProjectOverview = DarklabProjectOverview;
})(globalThis);
export {
  exportedDarklabProjectOverview as DarklabProjectOverview
};
