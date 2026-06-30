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
  const appCoverageLabels = {
    app_ports_found: "App ports found",
    scanned_no_ports_seen: "Scanned, no ports surfaced",
    not_scanned: "No app scan"
  };
  const reviewStages = [
    { key: "new", label: "New" },
    { key: "reviewed", label: "Reviewed" },
    { key: "important_followup", label: "Important/follow-up" }
  ];
  const verificationStages = [
    { key: "not_started", label: "Not started" },
    { key: "ready_to_verify", label: "Ready" },
    { key: "verified", label: "Verified" },
    { key: "needs_retest", label: "Needs retest" }
  ];
  const TARGET_PREVIEW_LIMIT = 6;
  function createProjectOverviewController(context) {
    const ctx = context || {};
    const states = /* @__PURE__ */ new Map();
    function defaultState() {
      return {
        error: "",
        loaded: false,
        loading: false,
        payload: null,
        hideEmptyTargets: false,
        targetsExpanded: false
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
    function logLevelForStatus(status) {
      const code = Number(status || 0);
      if (!code || code >= 500) return "error";
      return "warn";
    }
    function logClientEvent(eventName, err, details = {}) {
      if (typeof ctx.logClientError !== "function") return;
      const payload = { page: "project_overview", ...details };
      ctx.logClientError(`${eventName} ${JSON.stringify(payload)}`, err, {
        event: eventName,
        level: payload.level || "warn",
        page: "project_overview",
        phase: payload.phase || "",
        selection_key: payload.selection_key || "",
        status: payload.status || 0
      });
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
        if (!resp.ok) {
          const err = await responseError(resp, "Could not load project overview.");
          err.status = Number(resp.status || 0);
          throw err;
        }
        const payload = await resp.json();
        st.payload = payload && typeof payload === "object" ? payload : {};
        st.loaded = true;
      } catch (err) {
        const status = Number(err?.status || err?.statusCode || 0);
        st.error = err && err.message ? err.message : "Could not load project overview.";
        logClientEvent("PROJECT_OVERVIEW_CLIENT_LOAD_FAILED", err, {
          level: logLevelForStatus(status),
          phase: "load",
          selection_key: `project:${normalized}`,
          status
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
    function operationalTempo(st) {
      const payload = st && st.payload && typeof st.payload === "object" ? st.payload : {};
      return payload.operational_tempo && typeof payload.operational_tempo === "object" ? payload.operational_tempo : {};
    }
    function recentActivity(st) {
      const payload = st && st.payload && typeof st.payload === "object" ? st.payload : {};
      return Array.isArray(payload.recent_activity) ? payload.recent_activity : [];
    }
    function coverageGaps(st) {
      const payload = st && st.payload && typeof st.payload === "object" ? st.payload : {};
      return payload.coverage_gaps && typeof payload.coverage_gaps === "object" ? payload.coverage_gaps : {};
    }
    function deliverablesStatus(st) {
      const payload = st && st.payload && typeof st.payload === "object" ? st.payload : {};
      return payload.deliverables_status && typeof payload.deliverables_status === "object" ? payload.deliverables_status : {};
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
      return String(value || "").replace(/[._-]+/g, " ").replace(/\s+/g, " ").trim();
    }
    function eventLabel(value) {
      const readable = readableToken(value);
      return readable ? readable.replace(/\b\w/g, (letter) => letter.toUpperCase()) : "Activity";
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
    function freshnessLabel(value) {
      const normalized = String(value || "not_started");
      if (normalized === "fresh") return "Report fresh";
      if (normalized === "stale") return "Report stale";
      if (normalized === "no_finding_activity") return "No finding changes";
      return "No report";
    }
    function freshnessTone(value) {
      const normalized = String(value || "not_started");
      if (normalized === "fresh") return "badge-tone-green";
      if (normalized === "stale") return "badge-tone-amber";
      if (normalized === "no_finding_activity") return "badge-tone-cyan";
      return "badge-tone-muted";
    }
    function badge(label, tone = "badge-tone-muted", className = "", title = "") {
      const item = document.createElement("span");
      item.className = `badge ${tone}${className ? ` ${className}` : ""}`;
      item.textContent = String(label || "");
      if (title) item.title = title;
      return item;
    }
    function summaryCard(label, value, detail = "", tone = "", variant = "") {
      const card = document.createElement("div");
      card.className = [
        "project-overview-summary-card",
        tone ? `is-${tone}` : "",
        variant ? `is-${variant}` : ""
      ].filter(Boolean).join(" ");
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
    function renderSummaryGroup(label, cards) {
      const group = document.createElement("section");
      group.className = "project-overview-summary-group";
      const heading = document.createElement("div");
      heading.className = "project-overview-summary-heading";
      heading.textContent = label;
      const grid = document.createElement("div");
      grid.className = "project-overview-summary-grid";
      cards.forEach((card) => grid.appendChild(card));
      group.append(heading, grid);
      return group;
    }
    function renderRollups(st) {
      const source = rollups(st);
      const certs = source.certificate_statuses && typeof source.certificate_statuses === "object" ? source.certificate_statuses : {};
      const severities = source.finding_severities && typeof source.finding_severities === "object" ? source.finding_severities : {};
      const highSignal = Number(severities.critical || 0) + Number(severities.high || 0);
      const certAttention = Number(certs.expired || 0) + Number(certs.expiring_14d || 0) + Number(certs.expiring_30d || 0);
      const recentState = String(source.recent_change_state || "not-monitored");
      const targetCount = Number(source.target_count || 0);
      const scannedCount = Number(source.app_scan_target_count || 0);
      const scanPercent = targetCount > 0 ? Math.round(scannedCount / targetCount * 100) : 0;
      const wrap = document.createElement("div");
      wrap.className = "project-overview-summary";
      wrap.append(
        renderSummaryGroup("Coverage", [
          summaryCard("Targets", formatCount(source.target_count), `${formatCount(source.provider_count)} cached providers`),
          summaryCard("App scan coverage", `${formatCount(scannedCount)} of ${formatCount(targetCount)}`, `${formatCount(scanPercent)}% · ${formatCount(source.unscanned_target_count)} unscanned`)
        ]),
        renderSummaryGroup("Evidence", [
          summaryCard("App-native ports", formatCount(source.app_port_count), `${formatCount(source.app_port_target_count)} targets`),
          summaryCard("Cached provider ports", formatCount(source.open_port_count), `${formatCount(source.service_count)} services`),
          summaryCard("Provider/app drift", formatCount(source.port_divergence_target_count), "targets differ", Number(source.port_divergence_target_count || 0) ? "attention" : "")
        ]),
        renderSummaryGroup("Risk/work", [
          summaryCard("High-risk targets", formatCount(highSignal), "critical/high finding", highSignal ? "attention" : ""),
          summaryCard("Verification gaps", formatCount(source.awaiting_verification_target_count), "targets waiting", Number(source.awaiting_verification_target_count || 0) ? "attention" : ""),
          summaryCard("Certificates", formatCount(certAttention), "expired or expiring", certAttention ? "attention" : ""),
          summaryCard("Recent changes", recentLabels[recentState] || readableToken(recentState), "")
        ])
      );
      return wrap;
    }
    function renderProviderIntelCaveat() {
      const wrap = document.createElement("div");
      wrap.className = "project-overview-provider-caveat";
      wrap.appendChild(badge("Cached provider data", "badge-tone-muted"));
      const text = document.createElement("span");
      text.textContent = "App-captured ports and services are shown first; provider data comes from saved intel snapshots.";
      text.title = "Provider ports, services, certificates, and highlights come from saved intel snapshots.";
      wrap.appendChild(text);
      return wrap;
    }
    function findingCounts(target) {
      const counts = target?.finding_counts && typeof target.finding_counts === "object" ? target.finding_counts : {};
      return {
        review: counts.by_review_state && typeof counts.by_review_state === "object" ? counts.by_review_state : {},
        verification: counts.by_verification_state && typeof counts.by_verification_state === "object" ? counts.by_verification_state : {},
        suppressed: Number(counts.suppressed || 0)
      };
    }
    function findingProgressRollup(st) {
      const result = {
        review: {
          new: 0,
          reviewed: 0,
          important_followup: 0,
          false_positive: 0
        },
        verification: {
          not_started: 0,
          ready_to_verify: 0,
          verified: 0,
          needs_retest: 0,
          not_applicable: 0
        },
        suppressed: 0
      };
      targets(st).forEach((target) => {
        const counts = findingCounts(target);
        result.review.new += Number(counts.review.new || 0);
        result.review.reviewed += Number(counts.review.reviewed || 0);
        result.review.important_followup += Number(counts.review.important || 0) + Number(counts.review.needs_followup || 0);
        result.review.false_positive += Number(counts.review.false_positive || 0);
        result.verification.not_started += Number(counts.verification.not_started || 0);
        result.verification.ready_to_verify += Number(counts.verification.ready_to_verify || 0);
        result.verification.verified += Number(counts.verification.verified || 0);
        result.verification.needs_retest += Number(counts.verification.needs_retest || 0);
        result.verification.not_applicable += Number(counts.verification.not_applicable || 0);
        result.suppressed += counts.suppressed;
      });
      return result;
    }
    function renderProgressStage(stage, count) {
      const item = document.createElement("span");
      item.className = "project-overview-progress-stage";
      const value = document.createElement("strong");
      value.textContent = formatCount(count);
      const label = document.createElement("span");
      label.textContent = stage.label;
      item.append(value, label);
      return item;
    }
    function renderProgressRow(label, stages, counts, asideItems = []) {
      const row = document.createElement("section");
      row.className = "project-overview-progress-row";
      const title = document.createElement("div");
      title.className = "project-overview-progress-title";
      title.textContent = label;
      const track = document.createElement("div");
      track.className = "project-overview-progress-track";
      stages.forEach((stage) => track.appendChild(renderProgressStage(stage, counts[stage.key] || 0)));
      row.append(title, track);
      const asides = asideItems.filter((item) => Number(item.count || 0) > 0);
      if (asides.length) {
        const aside = document.createElement("div");
        aside.className = "project-overview-progress-asides";
        asides.forEach((item) => {
          aside.appendChild(badge(`${item.label}: ${formatCount(item.count)}`, item.tone || "badge-tone-muted"));
        });
        row.appendChild(aside);
      }
      return row;
    }
    function renderFindingProgress(st) {
      const counts = findingProgressRollup(st);
      const wrap = document.createElement("div");
      wrap.className = "project-overview-progress";
      wrap.append(
        renderProgressRow("Triage", reviewStages, counts.review, [
          { label: "False positive", count: counts.review.false_positive, tone: "badge-tone-muted" },
          { label: "Suppressed", count: counts.suppressed, tone: "badge-tone-muted" }
        ]),
        renderProgressRow("Verification", verificationStages, counts.verification, [
          { label: "Not applicable", count: counts.verification.not_applicable, tone: "badge-tone-muted" }
        ])
      );
      return wrap;
    }
    function gapGroups(st) {
      const gaps = coverageGaps(st);
      return [
        {
          key: "untouched_targets",
          label: "No app scan",
          items: Array.isArray(gaps.untouched_targets) ? gaps.untouched_targets : []
        },
        {
          key: "awaiting_verification",
          label: "Awaiting verification",
          items: Array.isArray(gaps.awaiting_verification) ? gaps.awaiting_verification : []
        },
        {
          key: "needs_followup",
          label: "Needs follow-up",
          items: Array.isArray(gaps.needs_followup) ? gaps.needs_followup : []
        }
      ];
    }
    function gapHints(item) {
      const link = item?.deep_link && typeof item.deep_link === "object" ? item.deep_link : {};
      return link.hints && typeof link.hints === "object" ? link.hints : {};
    }
    function renderGapItem(projectId, item) {
      const link = item?.deep_link && typeof item.deep_link === "object" ? item.deep_link : {};
      const tab = String(link.tab || "").trim();
      const node = tab ? document.createElement("button") : document.createElement("span");
      node.className = "project-overview-gap-item";
      if (tab) {
        node.type = "button";
        node.dataset.projectOverviewGap = tab;
        node.addEventListener("click", (event) => {
          event.preventDefault();
          gotoTab(projectId, tab, gapHints(item));
        });
        ctx.bindProjectRuntimePressable?.(node);
      }
      const label = document.createElement("strong");
      label.textContent = String(item?.display_label || item?.entity_id || "Target");
      const detail = document.createElement("span");
      detail.textContent = String(item?.detail || "");
      node.append(label, detail);
      return node;
    }
    function renderCoverageGaps(projectId, st) {
      const groups = gapGroups(st).filter((group) => group.items.length);
      const wrap = document.createElement("section");
      wrap.className = "project-overview-gaps";
      if (!groups.length) {
        const empty = document.createElement("div");
        empty.className = "project-overview-gap-empty";
        empty.textContent = "No app-data gaps in the current target set";
        wrap.appendChild(empty);
        return wrap;
      }
      groups.forEach((group) => {
        const row = document.createElement("div");
        row.className = "project-overview-gap-group";
        const title = document.createElement("div");
        title.className = "project-overview-gap-title";
        title.textContent = `${group.label}: ${formatCount(group.items.length)}`;
        const items = document.createElement("div");
        items.className = "project-overview-gap-items";
        group.items.forEach((item) => items.appendChild(renderGapItem(projectId, item)));
        row.append(title, items);
        wrap.appendChild(row);
      });
      return wrap;
    }
    function renderDeliverablesStatus(st) {
      const status = deliverablesStatus(st);
      const wrap = document.createElement("section");
      wrap.className = "project-overview-deliverables";
      const grid = document.createElement("div");
      grid.className = "project-overview-deliverables-grid";
      grid.append(
        summaryCard(
          "Last package",
          status.last_package_at ? formatDate(status.last_package_at) : "No packages",
          status.last_package_name || status.last_package_id || ""
        ),
        summaryCard(
          "Package build",
          status.last_package_build_at ? formatDate(status.last_package_build_at) : "Not built",
          status.last_package_build_job_id || ""
        ),
        summaryCard(
          "Report saved",
          status.last_report_saved_at ? formatDate(status.last_report_saved_at) : "No report",
          status.last_report_id || ""
        ),
        summaryCard(
          "Report exported",
          status.last_report_exported_at ? formatDate(status.last_report_exported_at) : "Not exported",
          status.last_report_export_job_id || ""
        )
      );
      const footer = document.createElement("div");
      footer.className = "project-overview-deliverables-footer";
      footer.appendChild(badge(
        freshnessLabel(status.report_freshness),
        freshnessTone(status.report_freshness)
      ));
      const detail = document.createElement("span");
      detail.textContent = status.latest_finding_activity_at ? `Latest finding activity ${formatDate(status.latest_finding_activity_at)}` : "No finding activity yet";
      footer.appendChild(detail);
      wrap.append(grid, footer);
      return wrap;
    }
    function activityHints(item) {
      const link = item?.deep_link && typeof item.deep_link === "object" ? item.deep_link : {};
      const targetId = String(link.target_id || item?.target_id || "").trim();
      const targetType = String(link.target_type || item?.target_type || "").trim();
      const hints = {};
      if (targetId && (targetType === "entity" || targetType === "target")) {
        hints.target_id = targetId;
      }
      if (targetType === "run" && targetId) hints.run_id = targetId;
      return hints;
    }
    function renderActivityItem(projectId, item) {
      const link = item?.deep_link && typeof item.deep_link === "object" ? item.deep_link : {};
      const tab = String(link.tab || "").trim();
      const node = tab ? document.createElement("button") : document.createElement("span");
      node.className = "project-overview-activity-item";
      if (tab) {
        node.type = "button";
        node.dataset.projectOverviewActivity = tab;
        node.addEventListener("click", (event) => {
          event.preventDefault();
          gotoTab(projectId, tab, activityHints(item));
        });
        ctx.bindProjectRuntimePressable?.(node);
      }
      const label = document.createElement("strong");
      label.textContent = eventLabel(item?.event_type);
      const meta = document.createElement("span");
      meta.textContent = [
        formatDate(item?.created),
        String(item?.summary || "")
      ].filter(Boolean).join(" · ");
      node.append(label, meta);
      return node;
    }
    function renderOperationalTempo(projectId, st) {
      const tempo = operationalTempo(st);
      const wrap = document.createElement("section");
      wrap.className = "project-overview-tempo";
      const metrics = document.createElement("div");
      metrics.className = "project-overview-tempo-grid";
      metrics.append(
        summaryCard("Last run", tempo.last_run_at ? formatDate(tempo.last_run_at) : "No runs", tempo.last_run_id || ""),
        summaryCard("Runs 7d", formatCount(tempo.runs_last_7d), "linked runs"),
        summaryCard("Last triage", tempo.last_finding_triaged_at ? formatDate(tempo.last_finding_triaged_at) : "No triage", tempo.last_finding_triaged_id || ""),
        summaryCard("Last artifact", tempo.last_artifact_at ? formatDate(tempo.last_artifact_at) : "No artifacts", tempo.last_artifact_id || "")
      );
      wrap.appendChild(metrics);
      const activity = recentActivity(st);
      const strip = document.createElement("div");
      strip.className = "project-overview-activity-strip";
      if (activity.length) {
        activity.forEach((item) => strip.appendChild(renderActivityItem(projectId, item)));
      } else {
        const empty = document.createElement("span");
        empty.className = "project-overview-activity-empty";
        empty.textContent = "No recent activity";
        strip.appendChild(empty);
      }
      wrap.appendChild(strip);
      return wrap;
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
    function appPortLabel(item) {
      const port = Number(item?.port || 0);
      const proto = String(item?.proto || "").trim();
      if (!port) return "";
      const base = `${port}${proto ? `/${proto}` : ""}`;
      const service = String(item?.service || "").trim();
      const version = String(item?.version || "").trim();
      if (service && version) return `${base} ${service} (${version})`;
      if (service) return `${base} ${service}`;
      if (version) return `${base} (${version})`;
      return base;
    }
    function appPortChipList(target, limit = 4) {
      const ports = Array.isArray(target?.app_ports) ? target.app_ports : [];
      const labels = ports.map(appPortLabel).filter(Boolean);
      const wrap = document.createElement("div");
      wrap.className = "project-overview-port-badge-list";
      labels.slice(0, limit).forEach((label) => {
        const chip = badge(label, "badge-tone-muted", "project-overview-port-badge", label);
        wrap.appendChild(chip);
      });
      if (labels.length > limit) {
        const more = badge(
          `+${formatCount(labels.length - limit)} more`,
          "badge-tone-muted",
          "project-overview-port-badge is-more",
          labels.slice(limit).join(", ")
        );
        wrap.appendChild(more);
      }
      return wrap;
    }
    function providerPortText(target) {
      const ports = Array.isArray(target?.open_ports) ? target.open_ports : [];
      const services = Array.isArray(target?.services) ? target.services : [];
      if (!ports.length && !services.length) return "";
      const portText = ports.length ? ports.slice(0, 5).join(", ") : "No ports";
      const serviceText = services.length ? services.slice(0, 4).join(", ") : "No services";
      return `${portText} · ${serviceText}`;
    }
    function portDivergence(target) {
      const provenance = target?.port_provenance && typeof target.port_provenance === "object" ? target.port_provenance : {};
      const divergence = provenance.divergence && typeof provenance.divergence === "object" ? provenance.divergence : {};
      return {
        appOnly: Array.isArray(divergence.app_only) ? divergence.app_only : [],
        providerOnly: Array.isArray(divergence.provider_only) ? divergence.provider_only : [],
        hasDrift: !!divergence.has_drift
      };
    }
    function providerFreshnessValue(target) {
      const sourceFlags = target?.source_flags && typeof target.source_flags === "object" ? target.source_flags : {};
      if (!sourceFlags.has_intel) return "none";
      const checkedAt = String(target?.certificate?.last_checked_at || "");
      const staleText = sourceFlags.has_stale_intel ? "stale" : "current";
      return checkedAt ? `${staleText} · checked ${formatDate(checkedAt)}` : `${staleText} · no check time`;
    }
    function appEvidenceText(target) {
      const evidence = target?.app_evidence && typeof target.app_evidence === "object" ? target.app_evidence : {};
      const state = String(evidence.coverage_state || "not_scanned");
      const scanCount = Number(evidence.scan_run_count || 0);
      const portRunCount = Number(evidence.app_port_run_count || scanCount || 0);
      const portCount = Number(target?.app_port_count || 0);
      const label = appCoverageLabels[state] || readableToken(state) || "App scan evidence";
      const scopeNote = String(evidence.scope_note || "").trim();
      if (state === "app_ports_found") {
        return `${label}: ${formatCount(portCount)} port${portCount === 1 ? "" : "s"} from ${formatCount(portRunCount)} app run${portRunCount === 1 ? "" : "s"}${scopeNote ? ` · ${scopeNote}` : ""}`;
      }
      if (state === "scanned_no_ports_seen") {
        return `${label}: ${formatCount(scanCount)} run${scanCount === 1 ? "" : "s"}${scopeNote ? ` · ${scopeNote}` : ""}`;
      }
      return scopeNote ? `${label}: ${scopeNote}` : label;
    }
    function hasFindingWork(target) {
      const counts = findingCounts(target);
      const severity = String(target?.top_finding_severity || "");
      return Boolean(severity) || Number(counts.review.new || 0) > 0 || Number(counts.review.important || 0) > 0 || Number(counts.review.needs_followup || 0) > 0 || Number(counts.verification.not_started || 0) > 0 || Number(counts.verification.ready_to_verify || 0) > 0 || Number(counts.verification.needs_retest || 0) > 0;
    }
    function isUnscannedEmptyTarget(target) {
      const evidence = target?.app_evidence && typeof target.app_evidence === "object" ? target.app_evidence : {};
      const coverageState = String(evidence.coverage_state || "not_scanned");
      return coverageState === "not_scanned" && !hasFindingWork(target) && !target?.source_flags?.has_intel && !target?.source_flags?.has_stale_intel && !target?.source_flags?.has_recent_changes && (!Array.isArray(target?.app_ports) || target.app_ports.length === 0) && (!Array.isArray(target?.open_ports) || target.open_ports.length === 0) && (!Array.isArray(target?.services) || target.services.length === 0);
    }
    function findingProgressText(target) {
      const counts = findingCounts(target);
      const awaitingReview = Number(counts.review.new || 0);
      const needsVerification = Number(counts.verification.not_started || 0) + Number(counts.verification.ready_to_verify || 0) + Number(counts.verification.needs_retest || 0);
      const falsePositive = Number(counts.review.false_positive || 0);
      const parts = [];
      if (awaitingReview) parts.push(`${formatCount(awaitingReview)} new`);
      if (needsVerification) parts.push(`${formatCount(needsVerification)} awaiting verification`);
      if (falsePositive) parts.push(`${formatCount(falsePositive)} false positive`);
      if (counts.suppressed) parts.push(`${formatCount(counts.suppressed)} suppressed`);
      return parts.length ? `Findings: ${parts.join(" · ")}` : "Findings: no open review work";
    }
    function findingProgressValue(target) {
      const text = findingProgressText(target);
      return text.replace(/^Findings:\s*/, "");
    }
    function targetDetailRow(label, value) {
      const row = document.createElement("div");
      row.className = "project-overview-target-detail";
      const key = document.createElement("span");
      key.className = "project-overview-target-detail-label";
      key.textContent = `${label}: `;
      const body = document.createElement("span");
      body.className = "project-overview-target-detail-value";
      if (value && typeof value.nodeType === "number") body.appendChild(value);
      else body.textContent = String(value || "");
      row.append(key, body);
      return row;
    }
    function targetSummaryLine(target) {
      const parts = [];
      const evidence = target?.app_evidence && typeof target.app_evidence === "object" ? target.app_evidence : {};
      const coverageState = String(evidence.coverage_state || "not_scanned");
      if (Array.isArray(target?.app_ports) && target.app_ports.length) {
        parts.push(`${formatCount(Number(target?.app_port_count || target.app_ports.length))} app port${Number(target?.app_port_count || target.app_ports.length) === 1 ? "" : "s"}`);
      } else if (coverageState === "scanned_no_ports_seen") {
        parts.push("scanned, no app ports surfaced");
      } else if (coverageState === "not_scanned") {
        parts.push("not scanned");
      }
      if (target?.source_flags?.has_intel) {
        parts.push(target?.source_flags?.has_stale_intel ? "provider intel stale" : "provider intel current");
      } else {
        parts.push("no provider intel");
      }
      return parts.join(" · ");
    }
    function targetDetailRows(target) {
      const rows = [];
      const portList = appPortChipList(target);
      if (portList.childElementCount) rows.push(targetDetailRow("Ports", portList));
      const providerText = providerPortText(target);
      if (providerText) rows.push(targetDetailRow("Provider", providerText));
      const intelText = providerFreshnessValue(target);
      if (intelText && intelText !== "none") rows.push(targetDetailRow("Intel", intelText));
      const scanText = appEvidenceText(target);
      if (scanText && scanText !== appCoverageLabels.not_scanned) rows.push(targetDetailRow("Scan", scanText));
      const findings = findingProgressValue(target);
      if (findings && findings !== "no open review work") rows.push(targetDetailRow("Findings", findings));
      if (!rows.length) {
        const tail = document.createElement("div");
        tail.className = "project-overview-target-muted-tail";
        tail.textContent = targetSummaryLine(target);
        rows.push(tail);
      }
      return rows;
    }
    function applyEntityHints(projectId, hints, options = {}) {
      const targetId = String(hints?.target_id || "").trim();
      const runId = String(hints?.run_id || "").trim();
      const hostEntityId = String(hints?.host_entity_id || "").trim();
      const entityType = String(hints?.entity_type || "").trim().toLowerCase();
      const destinationTab = String(options.destinationTab || "entities").trim() || "entities";
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
      const hostSet = ctx.projectHostFilterSet?.(projectId);
      if (hostSet) {
        hostSet.clear();
        if (hostEntityId) hostSet.add(hostEntityId);
      }
      if (entityType && typeof ctx.setProjectEntityTab === "function") {
        ctx.setProjectEntityTab(entityType);
      } else if (entityType) {
        logClientEvent("PROJECT_OVERVIEW_NAVIGATION_DEGRADED", null, {
          level: "warn",
          phase: "navigate",
          destination_tab: destinationTab,
          entity_type: entityType,
          has_host_filter: Boolean(hostEntityId),
          selection_key: `project:${projectId}`
        });
      }
      logClientEvent("PROJECT_OVERVIEW_NAVIGATION_APPLIED", null, {
        level: "debug",
        phase: "navigate",
        destination_tab: destinationTab,
        entity_type: entityType,
        target_filter: Boolean(targetId),
        target_filter_count: targetId ? 1 : 0,
        run_filter: Boolean(runId),
        run_filter_count: runId ? 1 : 0,
        host_filter: Boolean(hostEntityId),
        host_filter_count: hostEntityId ? 1 : 0,
        selection_key: `project:${projectId}`
      });
    }
    function applyFindingHints(projectId, hints) {
      applyEntityHints(projectId, hints, { destinationTab: "findings" });
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
      else if (tab === "entities") applyEntityHints(projectId, hints || {}, { destinationTab: tab });
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
      if (certStatus === "expired" || certStatus === "expiring_14d" || certStatus === "expiring_30d") {
        chips.push(badge(
          `Cert: ${certificateText(target?.certificate)}`,
          certificateTone(certStatus),
          "project-overview-chip",
          "Certificate expiry status for this target"
        ));
      }
      if (target?.source_flags?.has_recent_changes) {
        chips.push(badge("Changed", "badge-tone-cyan", "project-overview-chip"));
      }
      const evidence = target?.app_evidence && typeof target.app_evidence === "object" ? target.app_evidence : {};
      const coverageState = String(evidence.coverage_state || "not_scanned");
      if (coverageState === "app_ports_found") {
        chips.push(badge(
          "App ports",
          "badge-tone-green",
          "project-overview-chip",
          evidence.scope_note || "App-captured scan output found ports for this target"
        ));
      } else if (coverageState === "scanned_no_ports_seen") {
        chips.push(badge(
          "Scanned",
          "badge-tone-cyan",
          "project-overview-chip",
          evidence.coverage_caveat || "App-captured scan output did not surface ports for this target"
        ));
      }
      if (portDivergence(target).hasDrift) {
        chips.push(badge(
          "Provider/app drift",
          "badge-tone-amber",
          "project-overview-chip",
          "App-captured ports and cached provider ports differ for this target"
        ));
      }
      if (target?.source_flags?.has_stale_intel) {
        chips.push(badge(
          "Intel: Stale",
          "badge-tone-amber",
          "project-overview-chip",
          "Cached provider data for this target is past its refresh window"
        ));
      }
      return chips;
    }
    function targetSeverityClass(target) {
      const tone = severityTone(target?.top_finding_severity);
      if (tone === "badge-tone-red") return "has-severity-red";
      if (tone === "badge-tone-amber") return "has-severity-amber";
      return "";
    }
    function renderTargetRow(projectId, target, { mobile = false } = {}) {
      const row = document.createElement("article");
      row.className = [
        "project-overview-target-row",
        mobile ? "is-mobile" : "panel-row",
        targetSeverityClass(target)
      ].filter(Boolean).join(" ");
      const main = document.createElement("div");
      main.className = "project-overview-target-main";
      const header = document.createElement("div");
      header.className = "project-overview-target-header";
      const title = document.createElement("div");
      title.className = "project-overview-target-title";
      title.textContent = targetTitle(target);
      const headerBadges = document.createElement("div");
      headerBadges.className = "project-overview-target-header-badges";
      const severity = String(target?.top_finding_severity || "");
      if (severity) {
        headerBadges.appendChild(badge(
          severityLabels[severity] || readableToken(severity),
          severityTone(severity),
          "project-overview-severity-badge",
          "Highest actionable finding severity for this target"
        ));
      }
      const findingSummary = findingProgressValue(target);
      if (findingSummary && findingSummary !== "no open review work") {
        headerBadges.appendChild(badge(
          findingSummary,
          "badge-tone-muted",
          "project-overview-finding-summary-badge",
          "Finding review and verification work for this target"
        ));
      }
      header.append(title, headerBadges);
      const meta = document.createElement("div");
      meta.className = "project-overview-target-meta";
      meta.textContent = targetMeta(target);
      const details = document.createElement("div");
      details.className = "project-overview-target-details";
      targetDetailRows(target).forEach((item) => details.appendChild(item));
      const chipWrap = document.createElement("div");
      chipWrap.className = "project-overview-target-chips";
      targetChips(target).forEach((chip) => chipWrap.appendChild(chip));
      main.append(header, meta, details);
      if (chipWrap.childElementCount) main.appendChild(chipWrap);
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
      const portHints = hints.ports && typeof hints.ports === "object" ? hints.ports : null;
      actions.append(
        makeTabButton(projectId, "Entities", "entities", hints.entities || {}, "ghost"),
        makeTabButton(projectId, "Findings", "findings", hints.findings || {}, target?.top_finding_severity ? "secondary" : "ghost")
      );
      if (portDivergence(target).hasDrift && portHints) {
        actions.appendChild(makeTabButton(projectId, "Ports", "entities", portHints, "secondary"));
      }
      row.append(main, actions);
      return row;
    }
    function filteredTargets(rows, st) {
      if (!st?.hideEmptyTargets) return rows;
      return rows.filter((target) => !isUnscannedEmptyTarget(target));
    }
    function renderTargetToolbar(rows, visibleRows, st) {
      const wrap = document.createElement("div");
      wrap.className = "project-overview-target-toolbar";
      const meta = document.createElement("span");
      meta.className = "project-overview-target-count";
      meta.textContent = visibleRows.length === rows.length ? `${formatCount(rows.length)} targets` : `Showing ${formatCount(visibleRows.length)} of ${formatCount(rows.length)} targets`;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "toggle-btn project-overview-worklist-filter-toggle";
      button.textContent = "Hide unscanned with no findings";
      button.setAttribute("aria-pressed", st?.hideEmptyTargets ? "true" : "false");
      button.dataset.projectOverviewAction = "toggle-empty-targets";
      button.addEventListener("click", (event) => {
        event.preventDefault();
        st.hideEmptyTargets = !st.hideEmptyTargets;
        st.targetsExpanded = false;
        if (ctx.mobileView?.() === "detail") ctx.renderProjectMobileDetail?.();
        else ctx.renderProjectExplorer?.();
      });
      ctx.bindProjectRuntimePressable?.(button);
      wrap.append(meta, button);
      return wrap;
    }
    function renderTargetList(projectId, rows, st, { mobile = false } = {}) {
      const wrap = document.createElement("div");
      wrap.className = "project-overview-target-section";
      const visibleRows = filteredTargets(rows, st);
      wrap.appendChild(renderTargetToolbar(rows, visibleRows, st));
      const list = document.createElement("div");
      list.className = "project-overview-target-list";
      const limit = Number(st?.targetsExpanded) ? visibleRows.length : TARGET_PREVIEW_LIMIT;
      visibleRows.slice(0, limit).forEach((target) => list.appendChild(renderTargetRow(projectId, target, { mobile })));
      if (!visibleRows.length) {
        const empty = document.createElement("div");
        empty.className = "project-overview-target-filter-empty";
        empty.textContent = "No targets match the current worklist filter.";
        list.appendChild(empty);
      }
      wrap.appendChild(list);
      if (visibleRows.length > TARGET_PREVIEW_LIMIT) {
        const footer = document.createElement("div");
        footer.className = "project-overview-target-list-footer";
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-ghost";
        button.textContent = st.targetsExpanded ? "Show fewer targets" : `Show all ${formatCount(visibleRows.length)} targets`;
        button.dataset.projectOverviewAction = "toggle-targets";
        button.addEventListener("click", (event) => {
          event.preventDefault();
          st.targetsExpanded = !st.targetsExpanded;
          if (mobile && ctx.mobileView?.() === "detail") ctx.renderProjectMobileDetail?.();
          else ctx.renderProjectExplorer?.();
        });
        ctx.bindProjectRuntimePressable?.(button);
        footer.appendChild(button);
        wrap.appendChild(footer);
      }
      return wrap;
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
      if (!st.loaded && !st.loading && !st.error) {
        load(normalized).catch((err) => {
          logClientEvent("PROJECT_OVERVIEW_CLIENT_RENDER_LOAD_FAILED", err, {
            level: "error",
            phase: "render-load",
            selection_key: `project:${normalized}`
          });
        });
      }
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
      root.appendChild(renderProviderIntelCaveat());
      root.appendChild(renderFindingProgress(st));
      root.appendChild(renderOperationalTempo(normalized, st));
      root.appendChild(renderCoverageGaps(normalized, st));
      root.appendChild(renderDeliverablesStatus(st));
      root.appendChild(renderRecentState(st));
      const rows = targets(st);
      if (!rows.length) {
        root.appendChild(ctx.emptyProjectPanel?.("No project targets yet.") || document.createTextNode("No project targets yet."));
      } else {
        root.appendChild(renderTargetList(normalized, rows, st, { mobile }));
      }
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
