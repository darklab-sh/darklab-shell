import {
  activeTeamScopeCan,
  teamScopeDeniedMessage
} from "./static-chunk-zq3stbfi.dfa2064403d5.js";
import "./static-chunk-poi5czx6.3f5c94749765.js";
import "./static-chunk-zpenfczu.1862ffb66041.js";
import {
  showConfirm
} from "./static-chunk-4m44pm74.0a8001fa1d52.js";
import "./static-chunk-2bgb52uq.a327269283bb.js";
import {
  enhanceAppSelects
} from "./static-chunk-yo5cjr7d.b86e0c93eff0.js";
import "./static-chunk-gwztcp24.e58b5ff85d88.js";
import "./static-chunk-2kxtimik.c9801087c7a7.js";

// app/static/js/features/projects/project_report.js
var exportedDarklabProjectReport = null;
(function initProjectReport(global) {
  if (typeof document === "undefined") return;
  function createProjectReportController(context) {
    const ctx = context || {};
    const stateByProject = /* @__PURE__ */ new Map();
    const reportJobPollMs = 750;
    const dateRangeHelp = "Expected format: YYYY-MM-DD to YYYY-MM-DD, for example 2026-06-01 to 2026-06-05.";
    const metadataFields = [
      ["engagement_name", "Engagement name", "input"],
      ["date_range", "Date range", "input", { placeholder: "2026-06-01 to 2026-06-05", title: dateRangeHelp }],
      ["operator", "Operator", "input"],
      ["client", "Client", "input"],
      ["contact", "Contact", "input"],
      ["executive_summary", "Executive summary", "textarea"],
      ["methodology", "Methodology", "textarea"],
      ["cover_notes", "Cover notes", "textarea"]
    ];
    const selectionKinds = [
      ["run_ids", "Runs", "run", (item) => item.command || item.id, (item) => ctx.formatDate?.(item.started) || item.id],
      ["target_ids", "Targets", "target", (item) => item.value || item.canonical_value || item.id, (item) => item.type || "target"],
      ["finding_ids", "Findings", "finding", (item) => item.title || item.raw_line || item.id, (item) => item.severity || item.review_state || "finding"],
      ["artifact_ids", "Artifacts", "artifact", (item) => item.display_name || item.workspace_path || item.id, (item) => ctx.projectArtifactDetail?.(item) || item.kind || "artifact"]
    ];
    const selectionPageLimit = 50;
    const selectionConfig = {
      run_ids: { payloadKey: "runs", endpoint: "runs", summaryKey: "runs" },
      target_ids: { payloadKey: "targets", endpoint: "targets", summaryKey: "targets" },
      finding_ids: { payloadKey: "findings", endpoint: "findings", summaryKey: "findings" },
      artifact_ids: { payloadKey: "artifacts", endpoint: "artifacts", summaryKey: "artifacts" }
    };
    const selectionFilterDefaults = {
      run_ids: { q: "" },
      artifact_ids: { q: "" },
      finding_ids: { q: "", review_state: "", severity: "" },
      target_ids: { q: "", type: "", auto_discovered: false }
    };
    const findingReviewFilterOptions = [
      ["", "All reviews"],
      ["new", "New"],
      ["reviewed", "Reviewed"],
      ["important", "Important"],
      ["false_positive", "False positive"],
      ["needs_followup", "Needs follow-up"]
    ];
    const findingSeverityFilterOptions = [
      ["", "All severities"],
      ["critical", "Critical"],
      ["high", "High"],
      ["medium", "Medium"],
      ["low", "Low"],
      ["info", "Info"]
    ];
    const targetTypeFilterOptions = [
      ["", "All target types"],
      ["domain", "Domains"],
      ["ip", "IPs"],
      ["url", "URLs"]
    ];
    function canMutateProjects() {
      const can = typeof activeTeamScopeCan === "function" ? activeTeamScopeCan : null;
      return typeof can === "function" ? can("mutate_projects") : true;
    }
    function deniedMessage() {
      const denied = typeof teamScopeDeniedMessage === "function" ? teamScopeDeniedMessage : null;
      return typeof denied === "function" ? denied("change team projects") : "View-only team members can't change team projects. Switch to Personal or ask for operator access.";
    }
    function defaultDraft() {
      return {
        metadata: Object.fromEntries(metadataFields.map(([key]) => [key, ""])),
        sections: [
          ["cover", "Cover"],
          ["executive_summary", "Executive summary"],
          ["scope_targets", "Scope and targets"],
          ["methodology", "Methodology"],
          ["findings_by_severity", "Findings by severity"],
          ["included_runs", "Included runs"],
          ["artifacts", "Artifacts"],
          ["appendix", "Appendix"]
        ].map(([type, title]) => ({ type, title, enabled: true })),
        selection: {
          run_ids: [],
          artifact_ids: [],
          finding_ids: [],
          target_ids: []
        },
        selection_modes: {
          run_ids: "all",
          artifact_ids: "all",
          finding_ids: "all",
          target_ids: "all"
        },
        selection_filters: clone(selectionFilterDefaults),
        selection_exclude_ids: {
          run_ids: [],
          artifact_ids: [],
          finding_ids: [],
          target_ids: []
        },
        export: {
          redaction_mode: "redacted",
          include_private_notes: false
        }
      };
    }
    function clone(value) {
      try {
        return JSON.parse(JSON.stringify(value || {}));
      } catch (_) {
        return {};
      }
    }
    function normalizeDraft(draft) {
      const base = defaultDraft();
      const raw = draft && typeof draft === "object" ? draft : {};
      const metadata = raw.metadata && typeof raw.metadata === "object" ? raw.metadata : {};
      const selection = raw.selection && typeof raw.selection === "object" ? raw.selection : {};
      const selectionModes = raw.selection_modes && typeof raw.selection_modes === "object" ? raw.selection_modes : {};
      const selectionFilters = raw.selection_filters && typeof raw.selection_filters === "object" ? raw.selection_filters : {};
      const selectionExcludeIds = raw.selection_exclude_ids && typeof raw.selection_exclude_ids === "object" ? raw.selection_exclude_ids : {};
      const exportPrefs = raw.export && typeof raw.export === "object" ? raw.export : {};
      const rawSections = Array.isArray(raw.sections) ? raw.sections : base.sections;
      const known = new Map(base.sections.map((section) => [section.type, section]));
      const sections = [];
      const seen = /* @__PURE__ */ new Set();
      rawSections.forEach((section) => {
        if (!section || typeof section !== "object") return;
        const type = String(section.type || "").trim();
        if (!known.has(type) || seen.has(type)) return;
        seen.add(type);
        sections.push({
          type,
          title: String(section.title || known.get(type).title || type),
          enabled: section.enabled !== false
        });
      });
      base.sections.forEach((section) => {
        if (!seen.has(section.type)) sections.push({ ...section });
      });
      return {
        metadata: {
          ...base.metadata,
          ...Object.fromEntries(metadataFields.map(([key]) => [key, String(metadata[key] || "")]))
        },
        sections,
        selection: {
          ...base.selection,
          ...Object.fromEntries(Object.keys(base.selection).map((key) => [
            key,
            Array.isArray(selection[key]) ? selection[key].map((value) => String(value || "")).filter(Boolean) : []
          ]))
        },
        selection_modes: {
          ...base.selection_modes,
          ...Object.fromEntries(Object.keys(base.selection_modes).map((key) => {
            const mode = String(selectionModes[key] || "all").trim().toLowerCase();
            return [key, mode === "manual" ? "manual" : "all"];
          }))
        },
        selection_filters: {
          ...clone(base.selection_filters),
          ...Object.fromEntries(Object.keys(base.selection_filters).map((key) => [
            key,
            normalizeSelectionFilter(key, selectionFilters[key])
          ]))
        },
        selection_exclude_ids: {
          ...base.selection_exclude_ids,
          ...Object.fromEntries(Object.keys(base.selection_exclude_ids).map((key) => [
            key,
            Array.isArray(selectionExcludeIds[key]) ? selectionExcludeIds[key].map((value) => String(value || "")).filter(Boolean) : []
          ]))
        },
        export: {
          redaction_mode: String(exportPrefs.redaction_mode || "redacted") === "raw" ? "raw" : "redacted",
          include_private_notes: !!exportPrefs.include_private_notes
        }
      };
    }
    function stateFor(projectId) {
      const normalized = String(projectId || "").trim();
      if (!stateByProject.has(normalized)) {
        stateByProject.set(normalized, {
          projectId: normalized,
          loading: false,
          saving: false,
          previewing: false,
          exporting: false,
          loaded: false,
          dirty: false,
          error: "",
          notice: "",
          report: null,
          updated: "",
          draft: defaultDraft(),
          preview: null,
          templates: [],
          selectionPages: {},
          selectionPageRequests: {},
          selectionItemLabels: {}
        });
      }
      return stateByProject.get(normalized);
    }
    function readJsonResponse(resp, fallbackMessage) {
      return Promise.resolve(resp).then(async (response) => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(data.error || data.message || fallbackMessage || "Request failed.");
        }
        return data;
      });
    }
    function projectUrl(projectId, suffix = "") {
      return `/projects/${encodeURIComponent(projectId)}/report${suffix}`;
    }
    function jsonRequestOptions(options = {}) {
      return {
        ...options,
        headers: {
          "Content-Type": "application/json",
          ...options.headers || {}
        }
      };
    }
    function renderProjectSurfaces() {
      ctx.renderProjectExplorer?.();
      if (ctx.mobileView?.() === "detail") ctx.renderProjectMobileDetail?.();
    }
    function selectedItems(summary, key) {
      if (key === "run_ids") return ctx.projectRunItems?.(summary) || [];
      if (key === "target_ids") return ctx.projectTargetItems?.(summary) || [];
      if (key === "finding_ids") return ctx.projectFindingItems?.(String(summary?.project?.id || ctx.getSelectedProjectId?.() || "")) || [];
      if (key === "artifact_ids") return ctx.projectArtifactItems?.(summary) || [];
      return [];
    }
    function selectionSet(st, key) {
      const explicit = st.draft.selection && Array.isArray(st.draft.selection[key]) ? st.draft.selection[key] : [];
      return new Set(explicit.map((value) => String(value || "")).filter(Boolean));
    }
    function selectionExclusionSet(st, key) {
      const excluded = st.draft.selection_exclude_ids && Array.isArray(st.draft.selection_exclude_ids[key]) ? st.draft.selection_exclude_ids[key] : [];
      return new Set(excluded.map((value) => String(value || "")).filter(Boolean));
    }
    function normalizeSelectionFilter(key, rawFilter) {
      const raw = rawFilter && typeof rawFilter === "object" ? rawFilter : {};
      if (key === "target_ids") {
        const type = String(raw.type || "").trim().toLowerCase();
        return {
          q: String(raw.q || "").trim().slice(0, 128),
          type: targetTypeFilterOptions.some(([value]) => value === type) ? type : "",
          auto_discovered: raw.auto_discovered === true || String(raw.auto_discovered || "").toLowerCase() === "true"
        };
      }
      if (key === "finding_ids") {
        const reviewState = String(raw.review_state || "").trim().toLowerCase();
        const severity = String(raw.severity || "").trim().toLowerCase();
        return {
          q: String(raw.q || "").trim().slice(0, 128),
          review_state: findingReviewFilterOptions.some(([value]) => value === reviewState) ? reviewState : "",
          severity: findingSeverityFilterOptions.some(([value]) => value === severity) ? severity : ""
        };
      }
      if (key === "run_ids" || key === "artifact_ids") {
        return { q: String(raw.q || "").trim().slice(0, 128) };
      }
      return {};
    }
    function selectionFilter(st, key) {
      if (!st.draft.selection_filters || typeof st.draft.selection_filters !== "object") {
        st.draft.selection_filters = clone(selectionFilterDefaults);
      }
      st.draft.selection_filters[key] = normalizeSelectionFilter(key, st.draft.selection_filters[key]);
      return st.draft.selection_filters[key];
    }
    function hasActiveSelectionFilter(st, key) {
      const filter = selectionFilter(st, key);
      return Object.values(filter).some((value) => {
        if (typeof value === "boolean") return value;
        return String(value || "").trim() !== "";
      });
    }
    function selectionFilterLogContext(st, key, offset = 0) {
      const filter = selectionFilter(st, key);
      const filterActive = {};
      Object.entries(filter).forEach(([field, value]) => {
        filterActive[field] = typeof value === "boolean" ? value : String(value || "").trim() !== "";
      });
      return {
        selection_key: key,
        offset: Math.max(0, Number(offset) || 0),
        limit: selectionPageLimit,
        filter_fields: Object.keys(filter),
        filter_active: filterActive,
        has_active_filter: Object.values(filterActive).some(Boolean)
      };
    }
    function selectionMode(st, key) {
      return String(st.draft.selection_modes?.[key] || "all") === "manual" ? "manual" : "all";
    }
    function itemId(item) {
      return String(item && item.id || "").trim();
    }
    function rememberSelectionItems(st, key, items, labelFn, detailFn) {
      if (!st.selectionItemLabels || typeof st.selectionItemLabels !== "object") st.selectionItemLabels = {};
      if (!st.selectionItemLabels[key] || typeof st.selectionItemLabels[key] !== "object") st.selectionItemLabels[key] = {};
      (Array.isArray(items) ? items : []).forEach((item) => {
        const id = itemId(item);
        if (!id) return;
        st.selectionItemLabels[key][id] = {
          id,
          label: String(labelFn?.(item) || id),
          detail: String(detailFn?.(item) || "")
        };
      });
    }
    function ensureSelectionKey(st, key) {
      if (!st.draft.selection || typeof st.draft.selection !== "object") st.draft.selection = {};
      if (!Array.isArray(st.draft.selection[key])) st.draft.selection[key] = [];
      if (!st.draft.selection_modes || typeof st.draft.selection_modes !== "object") st.draft.selection_modes = {};
      if (!Object.prototype.hasOwnProperty.call(st.draft.selection_modes, key)) st.draft.selection_modes[key] = "all";
      if (!st.draft.selection_exclude_ids || typeof st.draft.selection_exclude_ids !== "object") st.draft.selection_exclude_ids = {};
      if (!Array.isArray(st.draft.selection_exclude_ids[key])) st.draft.selection_exclude_ids[key] = [];
      selectionFilter(st, key);
    }
    function setSelectionMode(st, key, mode) {
      ensureSelectionKey(st, key);
      st.draft.selection_modes[key] = mode === "manual" ? "manual" : "all";
      st.draft.selection[key] = [];
      st.draft.selection_exclude_ids[key] = [];
    }
    function updateManualSelection(st, key, id, checked) {
      if (!id) return;
      ensureSelectionKey(st, key);
      if (selectionMode(st, key) === "all") {
        const excluded = selectionExclusionSet(st, key);
        if (checked) excluded.delete(id);
        else excluded.add(id);
        st.draft.selection[key] = [];
        st.draft.selection_exclude_ids[key] = Array.from(excluded);
        return;
      }
      const selected = selectionSet(st, key);
      if (checked) selected.add(id);
      else selected.delete(id);
      st.draft.selection[key] = Array.from(selected);
      st.draft.selection_exclude_ids[key] = [];
      st.draft.selection_modes[key] = "manual";
    }
    function selectionPageState(st, key) {
      if (!st.selectionPages || typeof st.selectionPages !== "object") st.selectionPages = {};
      if (!st.selectionPages[key]) {
        st.selectionPages[key] = {
          items: [],
          total: 0,
          limit: selectionPageLimit,
          offset: 0,
          loading: false,
          loaded: false,
          error: ""
        };
      }
      return st.selectionPages[key];
    }
    function compactIdList(values, limit = 3) {
      const ids = Array.from(values || []).map((value) => String(value || "").trim()).filter(Boolean);
      if (!ids.length) return "";
      const shown = ids.slice(0, limit).join(", ");
      return ids.length > limit ? `${shown}, +${ids.length - limit} more` : shown;
    }
    function renderSelectionPickedSummary(st, key, mode, title) {
      const ids = mode === "all" ? Array.from(selectionExclusionSet(st, key)) : Array.from(selectionSet(st, key));
      if (!ids.length) return null;
      const labels = st.selectionItemLabels?.[key] || {};
      const known = [];
      const unresolved = [];
      ids.forEach((id) => {
        if (labels[id]) known.push(labels[id]);
        else unresolved.push(id);
      });
      const note = document.createElement("div");
      note.className = "project-report-selection-picked";
      const heading = document.createElement("p");
      heading.className = "project-report-selection-picked-title";
      heading.textContent = mode === "all" ? `Excluded ${title.toLowerCase()}` : `Selected ${title.toLowerCase()}`;
      note.appendChild(heading);
      if (known.length) {
        const list = document.createElement("ul");
        known.slice(0, 5).forEach((item) => {
          const row = document.createElement("li");
          const label = document.createElement("strong");
          label.textContent = item.label || item.id;
          row.appendChild(label);
          if (item.detail) {
            const detail = document.createElement("small");
            detail.textContent = item.detail;
            row.appendChild(detail);
          }
          list.appendChild(row);
        });
        note.appendChild(list);
        if (known.length > 5) {
          const more = document.createElement("p");
          more.className = "project-report-selection-picked-more";
          more.textContent = `+${known.length - 5} more loaded item${known.length - 5 === 1 ? "" : "s"}`;
          note.appendChild(more);
        }
      }
      if (unresolved.length) {
        const unresolvedNote = document.createElement("p");
        unresolvedNote.className = "project-report-selection-picked-unresolved";
        unresolvedNote.textContent = `Not loaded yet: ${compactIdList(unresolved, 5)}`;
        note.appendChild(unresolvedNote);
      }
      return note;
    }
    function resetSelectionPage(st, key) {
      if (!st.selectionPages || typeof st.selectionPages !== "object") st.selectionPages = {};
      delete st.selectionPages[key];
    }
    function fallbackSelectionPage(st, key, summary) {
      const page = selectionPageState(st, key);
      const items = selectedItems(summary, key);
      if (page.loaded || page.loading || !items.length) return;
      const summaryTotal = Number(summary?.counts?.[selectionConfig[key]?.summaryKey] || items.length || 0) || items.length;
      if (summaryTotal > items.length) return;
      if (items.length > selectionPageLimit) return;
      page.items = items.slice(0, selectionPageLimit);
      page.total = summaryTotal;
      page.limit = selectionPageLimit;
      page.offset = 0;
      page.loaded = true;
    }
    function pageUrl(projectId, key, offset = 0) {
      const config = selectionConfig[key] || {};
      const params = new URLSearchParams();
      params.set("limit", String(selectionPageLimit));
      params.set("offset", String(Math.max(0, Number(offset) || 0)));
      const st = stateFor(projectId);
      const filter = selectionFilter(st, key);
      if (key === "run_ids" || key === "artifact_ids") {
        if (filter.q) params.set("q", filter.q);
      }
      if (key === "target_ids") {
        if (filter.q) params.set("q", filter.q);
        if (filter.type) params.set("type", filter.type);
        if (filter.auto_discovered) params.set("auto_discovered", "1");
      }
      if (key === "finding_ids") {
        params.set("include_group_counts", "0");
        params.set("orphan_filter", "all");
        if (filter.q) params.set("q", filter.q);
        if (filter.review_state) params.set("review_state", filter.review_state);
        if (filter.severity) params.set("severity", filter.severity);
      }
      return `/projects/${encodeURIComponent(projectId)}/${config.endpoint}?${params.toString()}`;
    }
    function restoreReportEditorScroll(projectId, scrollTop) {
      if (!Number.isFinite(Number(scrollTop)) || Number(scrollTop) <= 0) return;
      const apply = () => {
        const root = visibleRoot(projectId);
        const editor = root?.querySelector?.(".project-report-editor");
        if (editor) editor.scrollTop = Number(scrollTop);
      };
      apply();
      window.requestAnimationFrame?.(apply);
      window.setTimeout?.(apply, 0);
    }
    async function loadSelectionPage(projectId, key, offset = 0, { render = true } = {}) {
      const st = stateFor(projectId);
      const page = selectionPageState(st, key);
      if (!selectionConfig[key] || page.loading) return page;
      if (!st.selectionPageRequests || typeof st.selectionPageRequests !== "object") {
        st.selectionPageRequests = {};
      }
      const requestId = Number(st.selectionPageRequests[key] || 0) + 1;
      st.selectionPageRequests[key] = requestId;
      page.loading = true;
      page.error = "";
      const isCurrentRequest = () => st.selectionPageRequests?.[key] === requestId && st.selectionPages?.[key] === page;
      try {
        const resp = await ctx.apiFetch(pageUrl(projectId, key, offset), { cache: "no-store" });
        const data = await readJsonResponse(resp, `Unable to load ${key.replace(/_/g, " ")}.`);
        if (!isCurrentRequest()) return selectionPageState(st, key);
        const payloadKey = selectionConfig[key].payloadKey;
        page.items = Array.isArray(data[payloadKey]) ? data[payloadKey] : [];
        page.total = Math.max(0, Number(data.total || page.items.length || 0) || 0);
        page.limit = Math.max(1, Number(data.limit || selectionPageLimit) || selectionPageLimit);
        page.offset = Math.max(0, Number(data.offset || offset) || 0);
        page.loaded = true;
      } catch (err) {
        if (!isCurrentRequest()) return selectionPageState(st, key);
        page.error = err?.message || `Unable to load ${key.replace(/_/g, " ")}.`;
        ctx.logClientError?.("failed to load report selector page", err, selectionFilterLogContext(st, key, offset));
      } finally {
        if (isCurrentRequest()) {
          page.loading = false;
          if (render) renderProjectSurfaces();
        }
      }
      return page;
    }
    function ensureSelectionPages(projectId, summary) {
      const st = stateFor(projectId);
      let requested = false;
      selectionKinds.forEach(([key]) => {
        const page = selectionPageState(st, key);
        fallbackSelectionPage(st, key, summary);
        if (!page.loaded && !page.loading && selectionConfig[key]) {
          requested = true;
          loadSelectionPage(projectId, key, 0).catch(() => {
          });
        }
      });
      return !requested;
    }
    function refreshPreviewPanel(st, root) {
      const host = root?.querySelector?.(".project-report-preview-wrap");
      if (!host) return;
      host.replaceChildren();
      renderPreview(st, host);
    }
    function markDirty(st, root = null) {
      const hadPreview = !!st.preview;
      st.dirty = true;
      st.notice = "";
      st.error = "";
      if (hadPreview) {
        st.preview = null;
        refreshPreviewPanel(st, root);
      }
    }
    async function load(projectId, { render = true } = {}) {
      const st = stateFor(projectId);
      if (st.loading || st.loaded) return st;
      st.loading = true;
      st.error = "";
      if (render) renderProjectSurfaces();
      try {
        const resp = await ctx.apiFetch(projectUrl(projectId), { cache: "no-store" });
        const data = await readJsonResponse(resp, "Unable to load report draft.");
        st.report = data.report || null;
        st.updated = String(data.report?.updated || "");
        st.draft = normalizeDraft(data.report?.draft || {});
        st.templates = Array.isArray(data.templates) ? data.templates : [];
        st.preview = null;
        st.dirty = false;
        st.loaded = true;
      } catch (err) {
        st.error = err.message || "Unable to load report draft.";
        ctx.logClientError?.("failed to load project report", err);
      } finally {
        st.loading = false;
        if (render) renderProjectSurfaces();
      }
      return st;
    }
    function visibleRoot(projectId) {
      return Array.from(document.querySelectorAll("[data-project-report-root]")).find((root) => String(root.dataset.projectReportRoot || "") === String(projectId || "")) || null;
    }
    function syncEditableFields(st, root = visibleRoot(st.projectId)) {
      if (!root) return;
      metadataFields.forEach(([key]) => {
        const field = root.querySelector(`[data-project-report-metadata="${key}"]`);
        if (field) st.draft.metadata[key] = String(field.value || "");
      });
      root.querySelectorAll("[data-project-report-section-toggle]").forEach((input) => {
        const index = Number(input.dataset.projectReportSectionToggle || -1);
        if (Number.isInteger(index) && st.draft.sections[index]) {
          st.draft.sections[index].enabled = !!input.checked;
        }
      });
      const redaction = root.querySelector('[data-project-report-export="redaction_mode"]');
      if (redaction) st.draft.export.redaction_mode = String(redaction.value || "redacted") === "raw" ? "raw" : "redacted";
      const privateNotes = root.querySelector('[data-project-report-export="include_private_notes"]');
      if (privateNotes) st.draft.export.include_private_notes = !!privateNotes.checked;
    }
    function requestDraft(st) {
      const draft = clone(st.draft);
      if (!canMutateProjects()) {
        draft.export = {
          ...draft.export || {},
          redaction_mode: "redacted",
          include_private_notes: false
        };
      }
      return draft;
    }
    async function save(projectId, root = visibleRoot(projectId)) {
      const st = stateFor(projectId);
      if (!canMutateProjects()) {
        st.error = deniedMessage();
        renderProjectSurfaces();
        return;
      }
      syncEditableFields(st, root);
      st.saving = true;
      st.error = "";
      renderProjectSurfaces();
      try {
        const resp = await ctx.apiFetch(projectUrl(projectId), jsonRequestOptions({
          method: "POST",
          body: JSON.stringify({
            draft: st.draft,
            expected_updated: st.updated || ""
          })
        }));
        const data = await readJsonResponse(resp, "Unable to save report draft.");
        st.report = data.report || null;
        st.updated = String(data.report?.updated || "");
        st.draft = normalizeDraft(data.report?.draft || st.draft);
        st.dirty = false;
        st.notice = "Report draft saved.";
        ctx.setProjectWorkspaceMessage?.("Report draft saved.");
      } catch (err) {
        st.error = err.message || "Unable to save report draft.";
        ctx.logClientError?.("failed to save project report draft", err);
      } finally {
        st.saving = false;
        renderProjectSurfaces();
      }
    }
    async function preview(projectId, root = visibleRoot(projectId)) {
      const st = stateFor(projectId);
      syncEditableFields(st, root);
      st.previewing = true;
      st.error = "";
      renderProjectSurfaces();
      try {
        const resp = await ctx.apiFetch(projectUrl(projectId, "/preview"), jsonRequestOptions({
          method: "POST",
          body: JSON.stringify({ draft: requestDraft(st) })
        }));
        const data = await readJsonResponse(resp, "Unable to preview report.");
        st.preview = data.preview || null;
        st.notice = "Preview updated.";
      } catch (err) {
        st.error = err.message || "Unable to preview report.";
        ctx.logClientError?.("failed to preview project report", err);
      } finally {
        st.previewing = false;
        renderProjectSurfaces();
      }
    }
    function waitForReportJob(projectId, job) {
      let current = job && typeof job === "object" ? job : {};
      return new Promise((resolve, reject) => {
        const poll = async () => {
          if (String(current.status || "") === "complete") {
            resolve(current);
            return;
          }
          if (String(current.status || "") === "failed") {
            reject(new Error(current.error || "Unable to export report."));
            return;
          }
          const st = stateFor(projectId);
          st.notice = `Preparing report archive: ${current.message || current.phase || "queued"}`;
          renderProjectSurfaces();
          window.setTimeout(async () => {
            try {
              const resp = await ctx.apiFetch(
                `${projectUrl(projectId, "/export-jobs")}/${encodeURIComponent(current.id || "")}`,
                { cache: "no-store" }
              );
              const data = await readJsonResponse(resp, "Unable to check report export status.");
              current = data.job || {};
              poll();
            } catch (err) {
              reject(err);
            }
          }, reportJobPollMs);
        };
        poll();
      });
    }
    async function exportReport(projectId, root = visibleRoot(projectId)) {
      const st = stateFor(projectId);
      syncEditableFields(st, root);
      st.exporting = true;
      st.error = "";
      renderProjectSurfaces();
      try {
        const startResp = await ctx.apiFetch(projectUrl(projectId, "/export"), jsonRequestOptions({
          method: "POST",
          body: JSON.stringify({ draft: requestDraft(st) }),
          cache: "no-store"
        }));
        const startData = await readJsonResponse(startResp, "Unable to start report export.");
        const job = await waitForReportJob(projectId, startData.job || {});
        const ticketResp = await ctx.apiFetch(
          `${projectUrl(projectId, "/export-jobs")}/${encodeURIComponent(job.id || "")}/download-ticket`,
          { method: "POST", cache: "no-store" }
        );
        const ticketData = await readJsonResponse(ticketResp, "Unable to download report.");
        const name = reportArchiveName(ctx.selectedProject?.(), st.draft);
        ctx.downloadUrlAsAttachment?.(ticketData.url, name, "Report download started.");
        st.notice = "Report download started.";
      } catch (err) {
        st.error = err.message || "Unable to export report.";
        ctx.logClientError?.("failed to export project report", err);
      } finally {
        st.exporting = false;
        renderProjectSurfaces();
      }
    }
    function printReport(projectId) {
      const st = stateFor(projectId);
      if (!st.preview || !st.preview.html) {
        st.error = "Preview the report before printing or saving as PDF.";
        renderProjectSurfaces();
        return;
      }
      const printWindow = window.open("", "_blank");
      if (!printWindow || !printWindow.document) {
        st.error = "Unable to open the print window. Allow pop-ups and try again.";
        renderProjectSurfaces();
        return;
      }
      printWindow.document.open();
      printWindow.document.write(String(st.preview.html || ""));
      printWindow.document.close();
      printWindow.focus?.();
      window.setTimeout(() => {
        try {
          printWindow.print?.();
        } catch (err) {
          st.error = err.message || "Unable to start the browser print flow.";
          ctx.logClientError?.("failed to print project report", err);
          renderProjectSurfaces();
        }
      }, 0);
    }
    async function confirmReloadSavedDraft() {
      const confirmFn = typeof ctx.showConfirm === "function" ? ctx.showConfirm : typeof showConfirm === "function" ? showConfirm : null;
      if (confirmFn) {
        const choice = await confirmFn({
          body: {
            text: "Reload the saved report draft?",
            note: "Unsaved report edits will be discarded."
          },
          tone: "warning",
          actions: [
            { id: "cancel", label: "Cancel", role: "cancel" },
            { id: "reload", label: "Reload saved", tone: "warning" }
          ]
        });
        return choice === "reload";
      }
      if (typeof global.confirm === "function") {
        return global.confirm("Reload the saved report draft? Unsaved report edits will be discarded.");
      }
      return false;
    }
    function reportArchiveName(project, draft) {
      const raw = String(draft?.metadata?.engagement_name || project?.slug || project?.name || "engagement-report").trim().toLowerCase();
      const safe = raw.replace(/[^a-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "engagement-report";
      return `${safe}.zip`;
    }
    function applyTemplate(st, templateId) {
      const template = st.templates.find((item) => String(item.id || "") === String(templateId || ""));
      if (!template || !Array.isArray(template.sections)) return;
      st.draft.sections = normalizeDraft({ sections: template.sections }).sections;
      markDirty(st);
    }
    function moveSection(st, index, offset) {
      const sections = st.draft.sections;
      const nextIndex = index + offset;
      if (nextIndex < 0 || nextIndex >= sections.length) return;
      const [item] = sections.splice(index, 1);
      sections.splice(nextIndex, 0, item);
      markDirty(st);
    }
    function fieldLabel(key) {
      const match = metadataFields.find(([field]) => field === key);
      return match ? match[1] : key.replace(/_/g, " ");
    }
    function renderNotice(st, host) {
      const message = st.error || st.notice;
      if (!message) return;
      const note = document.createElement("div");
      note.className = `project-report-message${st.error ? " is-error" : ""}`;
      note.textContent = message;
      host.appendChild(note);
    }
    function renderMetadata(st, host) {
      const section = document.createElement("section");
      section.className = "project-report-panel project-report-metadata";
      const heading = document.createElement("h3");
      heading.textContent = "Metadata";
      section.appendChild(heading);
      const grid = document.createElement("div");
      grid.className = "project-report-field-grid";
      metadataFields.forEach(([key, label, type, options]) => {
        const wrap = document.createElement("label");
        wrap.className = type === "textarea" ? "project-report-field project-report-field-wide" : "project-report-field";
        wrap.textContent = label;
        const input = document.createElement(type === "textarea" ? "textarea" : "input");
        input.className = "form-control form-control-compact";
        input.dataset.projectReportMetadata = key;
        input.value = st.draft.metadata[key] || "";
        if (options?.placeholder) input.placeholder = options.placeholder;
        if (options?.title) {
          input.title = options.title;
          wrap.title = options.title;
        }
        if (type === "textarea") input.rows = key === "executive_summary" ? 5 : 4;
        wrap.appendChild(input);
        grid.appendChild(wrap);
      });
      section.appendChild(grid);
      host.appendChild(section);
    }
    function renderTemplates(st, host) {
      if (st.templates.length <= 1) return;
      const section = document.createElement("section");
      section.className = "project-report-panel project-report-templates";
      const label = document.createElement("label");
      label.textContent = "Template";
      const select = document.createElement("select");
      select.className = "form-select";
      select.dataset.projectReportTemplate = "1";
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "Choose a template";
      select.appendChild(placeholder);
      st.templates.forEach((template) => {
        const option = document.createElement("option");
        option.value = String(template.id || "");
        option.textContent = template.label || template.id || "Template";
        select.appendChild(option);
      });
      label.appendChild(select);
      section.appendChild(label);
      host.appendChild(section);
    }
    function renderSections(st, host) {
      const section = document.createElement("section");
      section.className = "project-report-panel project-report-sections";
      const heading = document.createElement("h3");
      heading.textContent = "Sections";
      section.appendChild(heading);
      st.draft.sections.forEach((item, index) => {
        const row = document.createElement("div");
        row.className = "project-report-section-row";
        const label = document.createElement("label");
        label.className = "project-report-check-row";
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = item.enabled !== false;
        checkbox.dataset.projectReportSectionToggle = String(index);
        const text = document.createElement("span");
        text.textContent = item.title || item.type;
        label.append(checkbox, text);
        const controls = document.createElement("div");
        controls.className = "project-report-section-controls";
        const up = button("↑", "Move up", "section-up");
        up.disabled = index === 0;
        up.dataset.sectionIndex = String(index);
        const down = button("↓", "Move down", "section-down");
        down.disabled = index === st.draft.sections.length - 1;
        down.dataset.sectionIndex = String(index);
        controls.append(up, down);
        row.append(label, controls);
        section.appendChild(row);
      });
      host.appendChild(section);
    }
    function button(text, title, action, role = "secondary") {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `btn btn-${role} btn-compact`;
      btn.textContent = text;
      btn.title = title;
      btn.dataset.projectReportAction = action;
      ctx.bindProjectRuntimePressable?.(btn);
      return btn;
    }
    function renderExportPrefs(st, host) {
      const section = document.createElement("section");
      section.className = "project-report-panel project-report-export-prefs";
      const heading = document.createElement("h3");
      heading.textContent = "Export";
      section.appendChild(heading);
      const redactionLabel = document.createElement("label");
      redactionLabel.textContent = "Redaction";
      const redaction = document.createElement("select");
      redaction.className = "form-select";
      redaction.dataset.projectReportExport = "redaction_mode";
      const canMutate = canMutateProjects();
      const displayExport = canMutate ? st.draft.export : { redaction_mode: "redacted", include_private_notes: false };
      redaction.disabled = !canMutate;
      [
        ["redacted", "Redacted"],
        ["raw", "Raw"]
      ].forEach(([value, label]) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = label;
        option.selected = displayExport.redaction_mode === value;
        redaction.appendChild(option);
      });
      redactionLabel.appendChild(redaction);
      const privateLabel = document.createElement("label");
      privateLabel.className = "project-report-check-row";
      const privateInput = document.createElement("input");
      privateInput.type = "checkbox";
      privateInput.checked = !!displayExport.include_private_notes;
      privateInput.disabled = !canMutate;
      privateInput.dataset.projectReportExport = "include_private_notes";
      const privateText = document.createElement("span");
      privateText.textContent = "Include private notes";
      privateLabel.append(privateInput, privateText);
      section.append(redactionLabel, privateLabel);
      if (!canMutate) {
        const note = document.createElement("p");
        note.className = "project-report-note";
        note.textContent = deniedMessage();
        section.appendChild(note);
      }
      host.appendChild(section);
    }
    function provenanceCountsFromItems(items) {
      const counts = {};
      (Array.isArray(items) ? items : []).forEach((item) => {
        const provenance = item?.provenance && typeof item.provenance === "object" ? item.provenance : null;
        const origin = String(provenance?.origin || item?.link_source || "").trim();
        if (!origin) return;
        counts[origin] = (counts[origin] || 0) + 1;
      });
      return counts;
    }
    function reportProvenanceManifest(st, summary) {
      const draft = st?.draft || defaultDraft();
      const runCounts = provenanceCountsFromItems(ctx.projectRunItems?.(summary));
      const targetCounts = provenanceCountsFromItems(ctx.projectTargetItems?.(summary));
      const counts = { ...runCounts };
      Object.entries(targetCounts).forEach(([origin, count]) => {
        counts[origin] = (counts[origin] || 0) + count;
      });
      const originSources = Object.keys(counts);
      const selectedCounts = Object.fromEntries(
        Object.entries(draft.selection || {}).map(([key, value]) => [key, Array.isArray(value) ? value.length : 0])
      );
      return {
        redaction_mode: draft.export?.redaction_mode || "redacted",
        include_private_notes: !!draft.export?.include_private_notes,
        selected_entity_ids: draft.selection || {},
        provenance: {
          schema_version: originSources.length ? 1 : "",
          kind: "engagement_report",
          build: {
            redaction_mode: draft.export?.redaction_mode || "redacted",
            include_private_notes: !!draft.export?.include_private_notes,
            selected_entity_ids: draft.selection || {},
            selected_entity_counts: selectedCounts
          },
          sources: {
            project_links: originSources.length ? { origin_sources: originSources, counts_by_origin: counts } : { origin_sources: [], note: "Source provenance is not present in this project view." }
          },
          privacy: {
            redaction_mode: draft.export?.redaction_mode || "redacted",
            private_notes_included: !!draft.export?.include_private_notes
          }
        }
      };
    }
    function renderProvenance(st, host, summary) {
      if (typeof ctx.projectProvenanceSummaryElement !== "function") return;
      const section = ctx.projectProvenanceSummaryElement(reportProvenanceManifest(st, summary), {
        fallbackKind: "engagement_report",
        title: "Provenance"
      });
      section.classList.add("project-report-panel");
      host.appendChild(section);
    }
    function filterSelect(options, value, key, field, label) {
      const select = document.createElement("select");
      select.className = "form-select form-select-compact";
      select.title = label;
      select.setAttribute("aria-label", label);
      select.dataset.projectReportSelectionFilter = field;
      select.dataset.selectionKey = key;
      options.forEach(([optionValue, optionLabel]) => {
        const option = document.createElement("option");
        option.value = optionValue;
        option.textContent = optionLabel;
        option.selected = optionValue === value;
        select.appendChild(option);
      });
      return select;
    }
    function renderSelectionFilters(st, key) {
      const filter = selectionFilter(st, key);
      const wrap = document.createElement("div");
      wrap.className = "project-report-selection-filters";
      if (key === "run_ids" || key === "artifact_ids") {
        wrap.classList.add("is-search-only");
        const search = document.createElement("input");
        search.type = "search";
        search.className = "form-control form-control-compact";
        search.placeholder = key === "run_ids" ? "Search runs" : "Search artifacts";
        search.title = search.placeholder;
        search.setAttribute("aria-label", search.placeholder);
        search.value = filter.q || "";
        search.dataset.projectReportSelectionFilter = "q";
        search.dataset.selectionKey = key;
        wrap.append(search);
      } else if (key === "target_ids") {
        const search = document.createElement("input");
        search.type = "search";
        search.className = "form-control form-control-compact";
        search.placeholder = "Search targets";
        search.title = "Search targets";
        search.setAttribute("aria-label", "Search targets");
        search.value = filter.q || "";
        search.dataset.projectReportSelectionFilter = "q";
        search.dataset.selectionKey = key;
        const type = filterSelect(targetTypeFilterOptions, filter.type || "", key, "type", "Target type");
        const autoLabel = document.createElement("label");
        autoLabel.className = "project-report-check-row project-report-filter-check";
        const auto = document.createElement("input");
        auto.type = "checkbox";
        auto.checked = !!filter.auto_discovered;
        auto.dataset.projectReportSelectionFilter = "auto_discovered";
        auto.dataset.selectionKey = key;
        const autoText = document.createElement("span");
        autoText.textContent = "Auto";
        autoLabel.append(auto, autoText);
        wrap.append(search, type, autoLabel);
      } else if (key === "finding_ids") {
        const search = document.createElement("input");
        search.type = "search";
        search.className = "form-control form-control-compact";
        search.placeholder = "Search findings";
        search.title = "Search findings";
        search.setAttribute("aria-label", "Search findings");
        search.value = filter.q || "";
        search.dataset.projectReportSelectionFilter = "q";
        search.dataset.selectionKey = key;
        wrap.append(
          search,
          filterSelect(findingReviewFilterOptions, filter.review_state || "", key, "review_state", "Finding review state"),
          filterSelect(findingSeverityFilterOptions, filter.severity || "", key, "severity", "Finding severity")
        );
      }
      return wrap.childElementCount ? wrap : null;
    }
    function updateSelectionFilter(st, root, input) {
      const key = String(input.dataset.selectionKey || "");
      const field = String(input.dataset.projectReportSelectionFilter || "");
      if (!selectionConfig[key] || !field) return false;
      const current = { ...selectionFilter(st, key) };
      if (input.type === "checkbox") current[field] = !!input.checked;
      else current[field] = String(input.value || "");
      st.draft.selection_filters[key] = normalizeSelectionFilter(key, current);
      resetSelectionPage(st, key);
      if (selectionMode(st, key) === "all") {
        st.draft.selection[key] = [];
        st.draft.selection_exclude_ids[key] = [];
      }
      markDirty(st, root);
      loadSelectionPage(st.projectId, key, 0).catch(() => {
      });
      return true;
    }
    function renderSelection(st, host, projectId, summary) {
      const section = document.createElement("section");
      section.className = "project-report-panel project-report-selection";
      const heading = document.createElement("h3");
      heading.textContent = "Included items";
      section.appendChild(heading);
      selectionKinds.forEach(([key, title, kind, labelFn, detailFn]) => {
        const page = selectionPageState(st, key);
        const items = Array.isArray(page.items) ? page.items : [];
        rememberSelectionItems(st, key, selectedItems(summary, key), labelFn, detailFn);
        rememberSelectionItems(st, key, items, labelFn, detailFn);
        const selected = selectionSet(st, key);
        const excluded = selectionExclusionSet(st, key);
        const mode = selectionMode(st, key);
        const total = Number(page.total || summary?.counts?.[selectionConfig[key]?.summaryKey] || items.length || 0) || 0;
        const group = document.createElement("div");
        group.className = "project-report-selection-group";
        const groupHeader = document.createElement("div");
        groupHeader.className = "project-report-selection-heading";
        const groupTitle = document.createElement("h4");
        groupTitle.textContent = title;
        const groupMeta = document.createElement("p");
        groupMeta.className = "project-report-selection-summary";
        groupMeta.setAttribute("aria-live", "polite");
        groupMeta.setAttribute("aria-atomic", "true");
        const loadedStart = items.length ? Number(page.offset || 0) + 1 : 0;
        const loadedEnd = items.length ? Math.min(total || items.length, Number(page.offset || 0) + items.length) : 0;
        const loadedLabel = total > items.length ? `${loadedStart}-${loadedEnd} of ${total}` : `${items.length} available`;
        const allSelectedCount = Math.max(0, (total || items.length) - excluded.size);
        groupMeta.textContent = mode === "all" ? `${hasActiveSelectionFilter(st, key) ? "All matching" : "All"} ${allSelectedCount} selected; showing ${loadedLabel}.` : `${selected.size} selected; showing ${loadedLabel}.`;
        const controls = document.createElement("div");
        controls.className = "project-report-selection-actions";
        const selectAll = button("All", `Select all ${title.toLowerCase()}`, "selection-all");
        selectAll.dataset.selectionKey = key;
        const clear = button("None", `Clear ${title.toLowerCase()}`, "selection-none");
        clear.dataset.selectionKey = key;
        controls.append(selectAll, clear);
        const paging = document.createElement("div");
        paging.className = "project-report-selection-paging";
        const prev = button("Previous", `Previous ${title.toLowerCase()} page`, "selection-prev");
        prev.dataset.selectionKey = key;
        prev.disabled = page.loading || Number(page.offset || 0) <= 0;
        const next = button("Next", `Next ${title.toLowerCase()} page`, "selection-next");
        next.dataset.selectionKey = key;
        next.disabled = page.loading || Number(page.offset || 0) + Number(page.limit || selectionPageLimit) >= total;
        paging.append(prev, next);
        controls.appendChild(paging);
        const titleWrap = document.createElement("div");
        titleWrap.append(groupTitle, groupMeta);
        groupHeader.append(titleWrap, controls);
        group.appendChild(groupHeader);
        const filters = renderSelectionFilters(st, key);
        if (filters) group.appendChild(filters);
        const selectionSummary = renderSelectionPickedSummary(st, key, mode, title);
        if (selectionSummary) group.appendChild(selectionSummary);
        if (page.loading) {
          group.appendChild(ctx.emptyProjectPanel?.(`Loading ${title.toLowerCase()}...`) || document.createElement("div"));
        } else if (page.error) {
          const error = document.createElement("div");
          error.className = "project-report-message is-error";
          error.textContent = page.error;
          group.appendChild(error);
        } else if (!items.length) {
          group.appendChild(ctx.emptyProjectPanel?.(`No ${title.toLowerCase()} available.`) || document.createElement("div"));
        } else {
          items.forEach((item) => {
            const id = itemId(item);
            const row = document.createElement("label");
            row.className = "project-report-check-row project-report-selection-row";
            const input = document.createElement("input");
            input.type = "checkbox";
            input.value = id;
            input.checked = mode === "all" ? !excluded.has(id) : selected.has(id);
            input.dataset.projectReportSelection = key;
            input.dataset.selectionKind = kind;
            const text = document.createElement("span");
            text.className = "project-report-selection-text";
            const titleEl = document.createElement("strong");
            titleEl.textContent = labelFn(item);
            const detailEl = document.createElement("small");
            detailEl.textContent = detailFn(item);
            text.append(titleEl, detailEl);
            row.append(input, text);
            group.appendChild(row);
          });
        }
        section.appendChild(group);
      });
      host.appendChild(section);
    }
    function renderPreview(st, host) {
      const section = document.createElement("section");
      section.className = "project-report-preview";
      const header = document.createElement("div");
      header.className = "project-report-preview-header";
      const heading = document.createElement("h3");
      heading.textContent = "Preview";
      const actions = document.createElement("div");
      actions.className = "project-report-actions";
      const previewBtn = button(st.previewing ? "Previewing..." : "Preview", "Render preview", "preview", "secondary");
      previewBtn.disabled = !!st.previewing;
      const printBtn = button("Print/PDF", "Print or save the preview as PDF", "print", "secondary");
      printBtn.disabled = !st.preview?.html;
      const exportBtn = button(st.exporting ? "Exporting..." : "Export archive", "Export Markdown and HTML archive", "export", "primary");
      exportBtn.disabled = !!st.exporting;
      actions.append(previewBtn, printBtn, exportBtn);
      header.append(heading, actions);
      section.appendChild(header);
      if (st.preview && st.preview.html) {
        const frame = document.createElement("iframe");
        frame.className = "project-report-preview-frame";
        frame.setAttribute("title", "Report preview");
        frame.setAttribute("sandbox", "");
        frame.srcdoc = String(st.preview.html || "");
        section.appendChild(frame);
      } else {
        section.appendChild(ctx.emptyProjectPanel?.("Preview the report to render the current draft.") || document.createElement("div"));
      }
      host.appendChild(section);
    }
    function renderToolbar(st, host, projectId) {
      const toolbar = document.createElement("div");
      toolbar.className = "project-report-toolbar";
      const saveBtn = button(st.saving ? "Saving..." : "Save draft", "Save report draft", "save", "primary");
      saveBtn.disabled = st.saving || !canMutateProjects();
      if (!canMutateProjects()) saveBtn.title = deniedMessage();
      const reloadBtn = button("Reload saved", "Reload saved report draft", "reload");
      toolbar.append(saveBtn, reloadBtn);
      const status = document.createElement("span");
      status.className = "project-report-dirty-state";
      status.textContent = st.dirty ? "Unsaved changes" : st.updated ? `Saved ${ctx.formatDate?.(st.updated) || st.updated}` : "Not saved";
      toolbar.appendChild(status);
      host.appendChild(toolbar);
    }
    function renderReport(container, projectId, summary) {
      const st = stateFor(projectId);
      if (!st.loaded && !st.loading) {
        load(projectId, { render: false }).finally(() => {
          renderProjectSurfaces();
        }).catch(() => {
        });
      }
      container.dataset.projectReportRoot = projectId;
      container.classList.add("project-report-root");
      if (st.loading) {
        container.appendChild(ctx.emptyProjectPanel?.("Loading report draft...") || document.createElement("div"));
        return;
      }
      const shell = document.createElement("div");
      shell.className = "project-report-layout";
      renderNotice(st, shell);
      renderToolbar(st, shell, projectId);
      const editor = document.createElement("div");
      editor.className = "project-report-editor nice-scroll";
      renderTemplates(st, editor);
      renderMetadata(st, editor);
      renderSections(st, editor);
      renderExportPrefs(st, editor);
      renderProvenance(st, editor, summary);
      ensureSelectionPages(projectId, summary);
      renderSelection(st, editor, projectId, summary);
      const previewHost = document.createElement("div");
      previewHost.className = "project-report-preview-wrap";
      renderPreview(st, previewHost);
      shell.append(editor, previewHost);
      container.appendChild(shell);
      const enhanceSelects = typeof enhanceAppSelects === "function" ? enhanceAppSelects : null;
      if (typeof enhanceSelects === "function") enhanceSelects(container);
    }
    function renderMobileReportTab(projectId, summary) {
      const fragment = document.createDocumentFragment();
      const st = stateFor(projectId);
      const wrap = document.createElement("div");
      wrap.className = "project-report-mobile";
      renderReport(wrap, projectId, summary);
      fragment.appendChild(wrap);
      return fragment;
    }
    function handleInput(event) {
      const root = event.target.closest?.("[data-project-report-root]");
      if (!root) return false;
      const projectId = String(root.dataset.projectReportRoot || "");
      const st = stateFor(projectId);
      const selectionFilterInput = event.target.closest?.("[data-project-report-selection-filter]");
      if (selectionFilterInput?.type === "search") {
        updateSelectionFilter(st, root, selectionFilterInput);
        return true;
      }
      syncEditableFields(st, root);
      markDirty(st, root);
      return true;
    }
    function handleChange(event) {
      const root = event.target.closest?.("[data-project-report-root]");
      if (!root) return false;
      const projectId = String(root.dataset.projectReportRoot || "");
      const st = stateFor(projectId);
      const template = event.target.closest?.("[data-project-report-template]");
      if (template) {
        applyTemplate(st, template.value);
        renderProjectSurfaces();
        return true;
      }
      const selectionFilterInput = event.target.closest?.("[data-project-report-selection-filter]");
      if (selectionFilterInput) {
        updateSelectionFilter(st, root, selectionFilterInput);
        renderProjectSurfaces();
        return true;
      }
      const selectionInput = event.target.closest?.("[data-project-report-selection]");
      if (selectionInput) {
        updateManualSelection(
          st,
          String(selectionInput.dataset.projectReportSelection || ""),
          String(selectionInput.value || ""),
          !!selectionInput.checked
        );
        markDirty(st, root);
        return true;
      }
      syncEditableFields(st, root);
      const hadPreview = !!st.preview;
      markDirty(st, root);
      if (event.target.closest?.("[data-project-report-export]") && hadPreview) {
        renderProjectSurfaces();
        preview(projectId, root).catch(() => {
        });
      }
      return true;
    }
    async function handleClick(event) {
      const actionEl = event.target.closest?.("[data-project-report-action]");
      if (!actionEl) return false;
      const root = actionEl.closest?.("[data-project-report-root]");
      if (!root) return false;
      event.preventDefault();
      const projectId = String(root.dataset.projectReportRoot || "");
      const st = stateFor(projectId);
      const action = String(actionEl.dataset.projectReportAction || "");
      if (action === "save") await save(projectId, root);
      else if (action === "preview") await preview(projectId, root);
      else if (action === "export") await exportReport(projectId, root);
      else if (action === "print") printReport(projectId);
      else if (action === "reload") {
        if (st.dirty && !await confirmReloadSavedDraft()) return true;
        stateByProject.delete(projectId);
        await load(projectId);
      } else if (action === "section-up" || action === "section-down") {
        moveSection(st, Number(actionEl.dataset.sectionIndex || 0), action === "section-up" ? -1 : 1);
        renderProjectSurfaces();
      } else if (action === "selection-all" || action === "selection-none") {
        const key = String(actionEl.dataset.selectionKey || "");
        setSelectionMode(st, key, action === "selection-all" ? "all" : "manual");
        root.querySelectorAll(`[data-project-report-selection="${key}"]`).forEach((input) => {
          input.checked = action === "selection-all";
        });
        markDirty(st, root);
      } else if (action === "selection-prev" || action === "selection-next") {
        const key = String(actionEl.dataset.selectionKey || "");
        const page = selectionPageState(st, key);
        const direction = action === "selection-prev" ? -1 : 1;
        const nextOffset = Math.max(0, Number(page.offset || 0) + direction * Number(page.limit || selectionPageLimit));
        const editor = root.querySelector?.(".project-report-editor");
        const scrollTop = Number(editor?.scrollTop || 0);
        await loadSelectionPage(projectId, key, nextOffset, { render: false });
        renderProjectSurfaces();
        restoreReportEditorScroll(projectId, scrollTop);
      }
      return true;
    }
    return {
      load,
      renderReport,
      renderMobileReportTab,
      handleInput,
      handleChange,
      handleClick,
      stateFor,
      normalizeDraft
    };
  }
  const DarklabProjectReport = {
    createProjectReportController
  };
  exportedDarklabProjectReport = DarklabProjectReport;
})(globalThis);
export {
  exportedDarklabProjectReport as DarklabProjectReport
};
