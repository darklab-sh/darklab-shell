import {
  bindDisclosure
} from "./static-chunk-lxs2zdd2.87dc9e4c1317.js";
import "./static-chunk-fik64llj.1291b1f4f79b.js";
import "./static-chunk-yu6ty7m2.96c3ee208a44.js";
import "./static-chunk-sgyzdmxn.7d1842f12a94.js";

// app/static/js/features/projects/project_activity.js
var exportedDarklabProjectActivity = null;
(function projectActivityModule(global) {
  "use strict";
  const targetTypes = [
    ["", "All targets"],
    ["project", "Project"],
    ["finding", "Finding"],
    ["target", "Target"],
    ["run", "Run"],
    ["package", "Package"],
    ["report", "Report"],
    ["file", "File"],
    ["label", "Label"],
    ["note", "Note"],
    ["import", "Import"]
  ];
  const targetWorkspaceTabs = {
    finding: "findings",
    package: "packages",
    report: "report",
    target: "details",
    entity: "entities",
    project: "details"
  };
  function createProjectActivityController(context) {
    const ctx = context || {};
    const states = /* @__PURE__ */ new Map();
    function stateFor(projectId) {
      const id = String(projectId || "");
      if (!states.has(id)) {
        states.set(id, {
          events: [],
          error: "",
          filters: {
            event_type: "",
            actor: "",
            target_type: "",
            target_id: "",
            date_from: "",
            date_to: ""
          },
          hasMore: false,
          limit: 25,
          loadRequestId: 0,
          loaded: false,
          loading: false,
          offset: 0,
          retentionDays: 0
        });
      }
      return states.get(id);
    }
    function hasFilters(st) {
      return Object.values(st.filters || {}).some((value) => String(value || "").trim());
    }
    function paramsFor(st) {
      const params = new URLSearchParams();
      Object.entries(st.filters || {}).forEach(([key, value]) => {
        const normalized = String(value || "").trim();
        if (normalized) params.set(key, normalized);
      });
      params.set("limit", String(st.limit));
      params.set("offset", String(st.offset));
      return params;
    }
    async function responseError(resp, fallback) {
      if (typeof ctx.projectResponseError === "function") {
        return ctx.projectResponseError(resp, fallback);
      }
      return new Error(fallback);
    }
    function logLoadFailure(projectId, err) {
      if (typeof ctx.logClientError !== "function") return;
      const payload = { project_id: String(projectId || "") };
      ctx.logClientError(`failed to load project activity ${JSON.stringify(payload)}`, err);
    }
    async function load(projectId, options = {}) {
      const st = stateFor(projectId);
      const requestId = st.loadRequestId + 1;
      st.loadRequestId = requestId;
      st.offset = Math.max(0, Number(options.offset ?? st.offset) || 0);
      st.loading = true;
      st.error = "";
      if (options.render !== false) ctx.renderProjectExplorer?.();
      try {
        const resp = await ctx.projectWorkspaceRequest(
          `/projects/${encodeURIComponent(projectId)}/activity?${paramsFor(st).toString()}`,
          { cache: "no-store" }
        );
        if (!resp.ok) throw await responseError(resp, "Could not load project activity.");
        const payload = await resp.json();
        if (requestId !== st.loadRequestId) return st.loaded;
        st.events = Array.isArray(payload.events) ? payload.events : [];
        st.hasMore = !!payload.has_more;
        st.limit = Math.max(1, Number(payload.limit || st.limit) || st.limit);
        st.offset = Math.max(0, Number(payload.offset || 0) || 0);
        st.retentionDays = Math.max(0, Number(payload.retention_days || 0) || 0);
        st.loaded = true;
      } catch (err) {
        if (requestId !== st.loadRequestId) return st.loaded;
        st.error = err && err.message ? err.message : "Could not load project activity.";
        logLoadFailure(projectId, err);
      } finally {
        if (requestId !== st.loadRequestId) return st.loaded;
        st.loading = false;
        if (options.render !== false) ctx.renderProjectExplorer?.();
      }
      return st.loaded;
    }
    function option(value, label, selectedValue) {
      const node = document.createElement("option");
      node.value = value;
      node.textContent = label;
      node.selected = String(value || "") === String(selectedValue || "");
      return node;
    }
    function field(labelText, key, value, { type = "text", placeholder = "" } = {}) {
      const label = document.createElement("label");
      label.className = "project-activity-field";
      label.textContent = labelText;
      const input = document.createElement("input");
      input.type = type;
      input.className = "form-control";
      input.dataset.projectActivityFilter = key;
      input.value = value || "";
      if (placeholder) input.placeholder = placeholder;
      label.appendChild(input);
      return label;
    }
    function selectField(labelText, key, value, choices) {
      const label = document.createElement("label");
      label.className = "project-activity-field";
      label.textContent = labelText;
      const select = document.createElement("select");
      select.className = "form-select";
      select.dataset.projectActivityFilter = key;
      choices.forEach(([choiceValue, choiceLabel]) => {
        select.appendChild(option(choiceValue, choiceLabel, value));
      });
      label.appendChild(select);
      return label;
    }
    function readFilters(root, st) {
      root.querySelectorAll("[data-project-activity-filter]").forEach((control) => {
        st.filters[control.dataset.projectActivityFilter] = String(control.value || "").trim();
      });
    }
    function resetFilters(st) {
      Object.keys(st.filters).forEach((key) => {
        st.filters[key] = "";
      });
      st.offset = 0;
    }
    function invalidate(projectId = "") {
      const id = String(projectId || "");
      if (id) {
        const st = stateFor(id);
        st.loaded = false;
        st.error = "";
        return;
      }
      states.forEach((st) => {
        st.loaded = false;
        st.error = "";
      });
    }
    function eventLabel(eventType) {
      return String(eventType || "").replace(/[._-]+/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
    }
    function actorLabel(event) {
      const actor = event && event.actor && typeof event.actor === "object" ? event.actor : {};
      const parts = [
        actor.display_name || actor.member_id || "",
        actor.role || ""
      ].map((value) => String(value || "").trim()).filter(Boolean);
      return parts.length ? parts.join(" · ") : "Personal";
    }
    function targetLabel(event) {
      const target = event && event.target && typeof event.target === "object" ? event.target : {};
      const type = String(target.type || "").trim();
      const id = String(target.id || "").trim();
      if (!type && !id) return "Project";
      return [type, id].filter(Boolean).join(":");
    }
    function detailSummary(details) {
      if (!details || typeof details !== "object") return "";
      const preferred = [
        "name",
        "label",
        "source",
        "review_state",
        "status",
        "redaction_mode",
        "package_id",
        "report_id",
        "file_path",
        "source_path",
        "destination_path",
        "path",
        "old_path",
        "new_path"
      ];
      const parts = [];
      preferred.forEach((key) => {
        const value = details[key];
        if (value === void 0 || value === null || value === "") return;
        parts.push(`${key.replace(/_/g, " ")}: ${String(value)}`);
      });
      if (!parts.length) {
        Object.entries(details).slice(0, 3).forEach(([key, value]) => {
          if (value === void 0 || value === null || value === "") return;
          parts.push(`${key.replace(/_/g, " ")}: ${String(value)}`);
        });
      }
      return parts.join(" · ");
    }
    function detailValueText(value) {
      if (Array.isArray(value)) {
        const items = value.filter((item) => item !== void 0 && item !== null && item !== "").map((item) => item && typeof item === "object" ? "[object]" : String(item));
        return items.length ? items.join(", ") : "none";
      }
      if (value && typeof value === "object") {
        const parts = Object.entries(value).filter(([, item]) => item !== void 0 && item !== null && item !== "").slice(0, 4).map(([key, item]) => `${key.replace(/_/g, " ")}: ${item && typeof item === "object" ? "[object]" : String(item)}`);
        return parts.length ? parts.join(" · ") : "not recorded";
      }
      if (value === void 0 || value === null || value === "") return "not recorded";
      return String(value);
    }
    function renderDetailList(details) {
      const list = document.createElement("dl");
      list.className = "project-activity-detail-list nice-scroll";
      const entries = details && typeof details === "object" ? Object.entries(details) : [];
      if (!entries.length) {
        const term = document.createElement("dt");
        term.textContent = "details";
        const value = document.createElement("dd");
        value.textContent = "not recorded";
        list.append(term, value);
        return list;
      }
      entries.forEach(([key, value]) => {
        const term = document.createElement("dt");
        term.textContent = String(key || "").replace(/_/g, " ");
        const detail = document.createElement("dd");
        detail.textContent = detailValueText(value);
        list.append(term, detail);
      });
      return list;
    }
    function bindDetailsDisclosure(toggle, panel) {
      const bindDisclosure2 = typeof bindDisclosure !== "undefined" && bindDisclosure || null;
      const disclosure = typeof bindDisclosure2 === "function" ? bindDisclosure2(toggle, {
        panel,
        openClass: null,
        hiddenClass: "u-hidden",
        preventFocusTheft: true,
        clearPressStyle: true
      }) : null;
      if (disclosure) return;
      toggle.addEventListener("click", () => {
        const expanded = toggle.getAttribute("aria-expanded") === "true";
        toggle.setAttribute("aria-expanded", expanded ? "false" : "true");
        panel.classList.toggle("u-hidden", expanded);
      });
    }
    function renderDetailsDisclosure(details, panelId) {
      const wrap = document.createElement("div");
      wrap.className = "project-activity-details";
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "project-activity-details-toggle";
      toggle.setAttribute("aria-expanded", "false");
      if (panelId) toggle.setAttribute("aria-controls", panelId);
      const chev = document.createElement("span");
      chev.className = "disclosure-chev";
      chev.textContent = "▸";
      chev.setAttribute("aria-hidden", "true");
      const label = document.createElement("span");
      label.textContent = "details";
      toggle.append(chev, label);
      const list = renderDetailList(details);
      list.classList.add("u-hidden");
      if (panelId) list.id = panelId;
      bindDetailsDisclosure(toggle, list);
      wrap.append(toggle, list);
      return wrap;
    }
    function linkOrText(text, href) {
      if (!href) {
        const span = document.createElement("span");
        span.textContent = text;
        return span;
      }
      const link = document.createElement("a");
      link.href = href;
      link.textContent = text;
      return link;
    }
    function renderTarget(projectId, event) {
      const target = event && event.target && typeof event.target === "object" ? event.target : {};
      const label = targetLabel(event);
      const href = String(target.href || "").trim();
      if (href) return linkOrText(label, href);
      const targetType = String(target.type || "").trim();
      const targetId = String(target.id || "").trim();
      const tab = targetWorkspaceTabs[targetType];
      if (!tab || !targetId) return linkOrText(label, "");
      const button = document.createElement("button");
      button.type = "button";
      button.className = "btn btn-ghost btn-compact project-activity-target-link";
      button.textContent = label;
      button.dataset.projectActivityAction = "open-target";
      button.dataset.projectId = String(projectId || "");
      button.dataset.targetTab = tab;
      button.dataset.targetType = targetType;
      button.dataset.targetId = targetId;
      ctx.bindProjectRuntimePressable?.(button);
      return button;
    }
    function renderFilters(projectId, st) {
      const form = document.createElement("div");
      form.className = "project-activity-filters";
      form.dataset.projectActivityFilters = projectId;
      form.append(
        field("Event type", "event_type", st.filters.event_type, { placeholder: "finding.review_change" }),
        field("Actor", "actor", st.filters.actor, { placeholder: "name or member id" }),
        selectField("Target type", "target_type", st.filters.target_type, targetTypes),
        field("Target id", "target_id", st.filters.target_id, { placeholder: "target id" }),
        field("From", "date_from", st.filters.date_from, { type: "date" }),
        field("To", "date_to", st.filters.date_to, { type: "date" })
      );
      const actions = document.createElement("div");
      actions.className = "project-activity-filter-actions";
      const apply = ctx.makeProjectButton ? ctx.makeProjectButton("Apply", "activity-apply", projectId) : document.createElement("button");
      apply.type = "button";
      apply.textContent = "Apply";
      apply.dataset.projectActivityAction = "apply";
      apply.dataset.projectId = projectId;
      const clear = ctx.makeProjectButton ? ctx.makeProjectButton("Clear", "activity-clear", projectId, "secondary") : document.createElement("button");
      clear.type = "button";
      clear.textContent = "Clear";
      clear.dataset.projectActivityAction = "clear";
      clear.dataset.projectId = projectId;
      actions.append(apply, clear);
      form.appendChild(actions);
      ctx.bindProjectRuntimePressable?.(apply);
      ctx.bindProjectRuntimePressable?.(clear);
      return form;
    }
    function renderEmpty(st) {
      const message = hasFilters(st) ? "No activity matches these filters." : "No project activity yet.";
      const panel = ctx.emptyProjectPanel ? ctx.emptyProjectPanel(message) : document.createElement("div");
      if (!ctx.emptyProjectPanel) panel.textContent = message;
      if (!hasFilters(st) && st.retentionDays > 0) {
        const note = document.createElement("p");
        note.className = "project-activity-retention-note";
        note.textContent = `Audit rows older than ${st.retentionDays} days may no longer be available.`;
        panel.appendChild(note);
      }
      return panel;
    }
    function renderRow(projectId, event, { mobile = false, index = 0 } = {}) {
      const row = document.createElement(mobile ? "article" : "tr");
      row.className = mobile ? "project-activity-mobile-row" : "project-activity-row";
      const summary = detailSummary(event.details);
      if (mobile) {
        const heading = document.createElement("div");
        heading.className = "project-activity-mobile-heading";
        const action = document.createElement("strong");
        action.textContent = eventLabel(event.event_type);
        const time = document.createElement("span");
        time.textContent = ctx.formatDate ? ctx.formatDate(event.created) : String(event.created || "");
        heading.append(action, time);
        const meta = document.createElement("div");
        meta.className = "project-activity-mobile-meta";
        meta.append(renderTarget(projectId, event));
        const actor = document.createElement("span");
        actor.textContent = actorLabel(event);
        meta.appendChild(actor);
        row.append(heading, meta);
        if (summary) {
          const summaryNode = document.createElement("p");
          summaryNode.className = "project-activity-summary";
          summaryNode.textContent = summary;
          row.appendChild(summaryNode);
        }
      } else {
        [
          ctx.formatDate ? ctx.formatDate(event.created) : String(event.created || ""),
          actorLabel(event),
          eventLabel(event.event_type)
        ].forEach((text) => {
          const cell = document.createElement("td");
          cell.textContent = text;
          row.appendChild(cell);
        });
        const targetCell = document.createElement("td");
        targetCell.appendChild(renderTarget(projectId, event));
        row.appendChild(targetCell);
        const summaryCell = document.createElement("td");
        summaryCell.textContent = summary || "Recorded activity";
        row.appendChild(summaryCell);
      }
      const safeId = String(event?.id || index).replace(/[^a-zA-Z0-9_-]/g, "-");
      const details = renderDetailsDisclosure(
        event.details,
        `project-activity-details-${safeId}-${mobile ? "mobile" : "row"}`
      );
      if (mobile) {
        row.appendChild(details);
      } else {
        const detailsCell = document.createElement("td");
        detailsCell.appendChild(details);
        row.appendChild(detailsCell);
      }
      return row;
    }
    function renderTable(projectId, st) {
      const wrap = document.createElement("div");
      wrap.className = "project-activity-table-wrap nice-scroll";
      const table = document.createElement("table");
      table.className = "project-activity-table";
      const thead = document.createElement("thead");
      const headRow = document.createElement("tr");
      ["Time", "Actor", "Action", "Target", "Summary", "Details"].forEach((label) => {
        const th = document.createElement("th");
        th.textContent = label;
        headRow.appendChild(th);
      });
      thead.appendChild(headRow);
      const tbody = document.createElement("tbody");
      st.events.forEach((event, index) => tbody.appendChild(renderRow(projectId, event, { index })));
      table.append(thead, tbody);
      wrap.appendChild(table);
      return wrap;
    }
    function renderMobileList(projectId, st) {
      const list = document.createElement("div");
      list.className = "project-activity-mobile-list";
      st.events.forEach((event, index) => list.appendChild(renderRow(projectId, event, { mobile: true, index })));
      return list;
    }
    function renderPager(projectId, st) {
      const pager = document.createElement("div");
      pager.className = "project-activity-pager";
      const status = document.createElement("span");
      const start = st.events.length ? st.offset + 1 : 0;
      const end = st.offset + st.events.length;
      status.textContent = st.events.length ? `${start}-${end} shown` : "0 shown";
      const prev = ctx.makeProjectButton ? ctx.makeProjectButton("Previous", "activity-prev", projectId, "secondary") : document.createElement("button");
      prev.type = "button";
      prev.textContent = "Previous";
      prev.dataset.projectActivityAction = "prev";
      prev.dataset.projectId = projectId;
      prev.disabled = st.offset <= 0 || st.loading;
      const next = ctx.makeProjectButton ? ctx.makeProjectButton("Next", "activity-next", projectId, "secondary") : document.createElement("button");
      next.type = "button";
      next.textContent = "Next";
      next.dataset.projectActivityAction = "next";
      next.dataset.projectId = projectId;
      next.disabled = !st.hasMore || st.loading;
      pager.append(status, prev, next);
      ctx.bindProjectRuntimePressable?.(prev);
      ctx.bindProjectRuntimePressable?.(next);
      return pager;
    }
    function render(projectId, summary, { mobile = false } = {}) {
      const st = stateFor(projectId);
      const root = document.createElement("div");
      root.className = mobile ? "project-activity-root project-activity-root-mobile" : "project-activity-root";
      root.dataset.projectActivityRoot = projectId;
      root.appendChild(renderFilters(projectId, st));
      if (st.loading) {
        root.appendChild(ctx.emptyProjectPanel ? ctx.emptyProjectPanel("Loading project activity...") : document.createTextNode("Loading project activity..."));
      } else if (st.error) {
        const panel = ctx.emptyProjectPanel ? ctx.emptyProjectPanel(st.error) : document.createElement("div");
        if (!ctx.emptyProjectPanel) panel.textContent = st.error;
        const retry = ctx.makeProjectButton ? ctx.makeProjectButton("Retry", "activity-retry", projectId, "secondary") : document.createElement("button");
        retry.type = "button";
        retry.textContent = "Retry";
        retry.dataset.projectActivityAction = "retry";
        retry.dataset.projectId = projectId;
        panel.appendChild(retry);
        ctx.bindProjectRuntimePressable?.(retry);
        root.appendChild(panel);
      } else if (!st.loaded) {
        root.appendChild(ctx.emptyProjectPanel ? ctx.emptyProjectPanel("Loading project activity...") : document.createTextNode("Loading project activity..."));
        load(projectId).catch(() => {
        });
      } else if (!st.events.length) {
        root.appendChild(renderEmpty(st));
      } else {
        root.appendChild(mobile ? renderMobileList(projectId, st) : renderTable(projectId, st));
        root.appendChild(renderPager(projectId, st));
      }
      if (summary && summary.project && summary.project.status === "archived") {
        const note = document.createElement("p");
        note.className = "project-activity-retention-note";
        note.textContent = "Archived project activity is read-only.";
        root.appendChild(note);
      }
      return root;
    }
    function renderActivity(container, projectId, summary) {
      container.replaceChildren(render(projectId, summary));
    }
    function renderMobileActivityTab(projectId, summary) {
      return render(projectId, summary, { mobile: true });
    }
    async function handleClick(event) {
      const action = event.target.closest?.("[data-project-activity-action]");
      if (!action) return false;
      event.preventDefault?.();
      const root = action.closest("[data-project-activity-root]") || action.closest("[data-project-activity-filters]");
      const projectId = String(action.dataset.projectId || root?.dataset.projectActivityRoot || root?.dataset.projectActivityFilters || "");
      if (!projectId) return true;
      const st = stateFor(projectId);
      const name = String(action.dataset.projectActivityAction || "");
      if (name === "open-target") {
        ctx.openProjectObject?.(projectId, {
          tab: String(action.dataset.targetTab || ""),
          targetType: String(action.dataset.targetType || ""),
          targetId: String(action.dataset.targetId || "")
        });
        return true;
      }
      if (name === "apply") {
        const filterRoot = action.closest("[data-project-activity-filters]") || root;
        readFilters(filterRoot, st);
        await load(projectId, { offset: 0 });
      } else if (name === "clear") {
        resetFilters(st);
        await load(projectId, { offset: 0 });
      } else if (name === "prev") {
        await load(projectId, { offset: Math.max(0, st.offset - st.limit) });
      } else if (name === "next") {
        await load(projectId, { offset: st.offset + st.limit });
      } else if (name === "retry") {
        await load(projectId);
      }
      return true;
    }
    return {
      handleClick,
      invalidate,
      load,
      renderActivity,
      renderMobileActivityTab,
      stateFor
    };
  }
  const DarklabProjectActivity = {
    createProjectActivityController
  };
  exportedDarklabProjectActivity = DarklabProjectActivity;
})(window);
export {
  exportedDarklabProjectActivity as DarklabProjectActivity
};
