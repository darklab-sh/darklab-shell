import {
  showWorkspaceViewer
} from "./static-chunk-pvsb2z2r.6329cc7a7aa9.js";
import "./static-chunk-poi5czx6.3f5c94749765.js";
import "./static-chunk-zpenfczu.1862ffb66041.js";
import "./static-chunk-4m44pm74.0a8001fa1d52.js";
import "./static-chunk-2bgb52uq.a327269283bb.js";
import "./static-chunk-yo5cjr7d.b86e0c93eff0.js";
import "./static-chunk-gwztcp24.e58b5ff85d88.js";
import "./static-chunk-2kxtimik.c9801087c7a7.js";

// app/static/js/features/projects/project_artifacts.js
var exportedDarklabProjectArtifacts = null;
(function projectArtifactsModule(global) {
  "use strict";
  function createProjectArtifactsController(context) {
    const ctx = context || {};
    const pages = /* @__PURE__ */ new Map();
    const allArtifacts = /* @__PURE__ */ new Map();
    const pageLimit = 50;
    function groupKey(projectId, runId) {
      return `${String(projectId || "")}${String(runId || "")}`;
    }
    function page(projectId) {
      const key = String(projectId || "");
      if (!pages.has(key)) pages.set(key, {
        artifacts: [],
        total: 0,
        runCounts: {},
        limit: pageLimit,
        offset: 0,
        filterKey: "",
        loading: false,
        loaded: false,
        error: ""
      });
      return pages.get(key);
    }
    function setPageOffset(projectId, offset = 0) {
      const state = page(projectId);
      state.offset = Math.max(0, Number(offset || 0));
      state.limit = pageLimit;
      state.loading = true;
      state.loaded = false;
    }
    function invalidate(projectId = "") {
      const normalized = String(projectId || "");
      if (!normalized) {
        pages.clear();
        allArtifacts.clear();
        return;
      }
      pages.delete(normalized);
      allArtifacts.delete(normalized);
    }
    function groupCollapsed(projectId, runId) {
      return ctx.collapsedArtifactGroups().has(groupKey(projectId, runId));
    }
    function items(summary) {
      const projectId = String(summary?.project?.id || ctx.selectedProjectId?.() || "");
      if (projectId && allArtifacts.has(projectId)) return allArtifacts.get(projectId);
      const state = page(projectId);
      return state.loaded ? state.artifacts : summary && Array.isArray(summary.artifacts) ? summary.artifacts : [];
    }
    function filesEnabled() {
      return !!ctx.filesEnabled();
    }
    function artifactsVisible() {
      return filesEnabled();
    }
    function status(artifact) {
      const artifactStatus = String(artifact && artifact.file_status || "").trim();
      if (artifactStatus === "available" || artifactStatus === "missing" || artifactStatus === "changed" || artifactStatus === "disabled") {
        return artifactStatus;
      }
      return artifact && artifact.file_available === false ? "missing" : "available";
    }
    function statusLabel(artifact) {
      const artifactStatus = status(artifact);
      if (artifactStatus === "disabled") return "disabled";
      if (artifactStatus === "changed") return "changed";
      if (artifactStatus === "missing") return "missing";
      return "available";
    }
    function accessory(projectId, artifact) {
      const wrap = document.createElement("div");
      wrap.className = "project-artifact-badges";
      const size = document.createElement("span");
      size.className = "project-explorer-item-badge";
      size.textContent = ctx.formatBytes(artifact.byte_size);
      const statusNode = document.createElement("span");
      statusNode.className = `project-artifact-status is-${status(artifact)}`;
      statusNode.textContent = statusLabel(artifact);
      wrap.append(size, statusNode);
      const actions = document.createElement("div");
      actions.className = "project-artifact-actions";
      const edit = document.createElement("button");
      edit.type = "button";
      edit.className = "btn btn-secondary btn-compact project-artifact-action";
      edit.dataset.projectAction = "edit-artifact-metadata";
      edit.dataset.projectId = String(projectId || "");
      edit.dataset.artifactId = String(artifact.id || "");
      edit.textContent = "Edit";
      ctx.bindProjectRuntimePressable(edit);
      actions.appendChild(edit);
      const artifactStatus = status(artifact);
      const available = artifactStatus !== "missing" && artifactStatus !== "disabled";
      [
        ["preview", "Preview"],
        ["download", "Download"]
      ].forEach(([actionName, label]) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn btn-secondary btn-compact project-artifact-action";
        btn.dataset.projectAction = `artifact-${actionName}`;
        btn.dataset.projectId = String(projectId || "");
        btn.dataset.artifactId = String(artifact.id || "");
        btn.dataset.artifactPath = String(artifact.workspace_path || "");
        btn.disabled = !available;
        btn.title = available ? label : artifact.file_status_detail || "Workspace file is unavailable";
        btn.textContent = label;
        ctx.bindProjectRuntimePressable(btn);
        actions.appendChild(btn);
      });
      wrap.appendChild(actions);
      return wrap;
    }
    function detail(artifact) {
      const parts = [
        artifact.kind || "file",
        artifact.content_type || "unknown type",
        ctx.formatDate(artifact.created)
      ];
      const artifactStatus = status(artifact);
      const statusDetail = String(artifact.file_status_detail || "").trim();
      if (artifactStatus === "changed") {
        parts.push(`current ${ctx.formatBytes(artifact.current_byte_size)}`);
      } else if (artifactStatus === "missing") {
        parts.push(statusDetail || "workspace file is missing");
      } else if (artifactStatus === "disabled") {
        parts.push(statusDetail || "Files are disabled on this instance");
      }
      return parts.filter(Boolean).join(ctx.metaSeparator || " - ");
    }
    function detailLines(artifact) {
      const artifactStatus = status(artifact);
      const statusDetail = String(artifact && artifact.file_status_detail || "").trim();
      const firstLine = [
        artifact && artifact.kind || "file",
        artifact && artifact.content_type || "unknown type"
      ].filter(Boolean).join(ctx.metaSeparator || " - ");
      const lines = [
        firstLine,
        ctx.formatDate(artifact && artifact.created)
      ].filter(Boolean);
      if (artifactStatus === "changed") {
        lines.push(`current ${ctx.formatBytes(artifact.current_byte_size)}`);
      } else if (artifactStatus === "missing") {
        lines.push(statusDetail || "workspace file is missing");
      } else if (artifactStatus === "disabled") {
        lines.push(statusDetail || "Files are disabled on this instance");
      }
      return lines;
    }
    function downloadName(artifactPath = "", fallback = "artifact") {
      const name = String(artifactPath || "").split("/").filter(Boolean).pop();
      return name || fallback;
    }
    function pagedItems(projectId, artifacts) {
      const allArtifacts2 = Array.isArray(artifacts) ? artifacts : [];
      const state = page(projectId);
      if (state.offset >= allArtifacts2.length) {
        state.offset = Math.max(0, Math.floor(Math.max(0, allArtifacts2.length - 1) / pageLimit) * pageLimit);
      }
      return allArtifacts2.slice(state.offset, state.offset + pageLimit);
    }
    function serverFilterParams(projectId, summary) {
      const params = new URLSearchParams();
      const runFilters = typeof ctx.projectRunFilterSet === "function" ? ctx.projectRunFilterSet(projectId) : /* @__PURE__ */ new Set();
      runFilters.forEach((runId) => {
        if (runId) params.append("run_id", runId);
      });
      const targetFilters = typeof ctx.projectTargetFilterSet === "function" ? ctx.projectTargetFilterSet(projectId) : /* @__PURE__ */ new Set();
      const targets = typeof ctx.projectTargetItems === "function" ? ctx.projectTargetItems(summary) : [];
      const availableTargets = new Set(
        (Array.isArray(targets) ? targets : []).map((target) => String(target && target.id || "")).filter(Boolean)
      );
      targetFilters.forEach((targetId) => {
        if (targetId && availableTargets.has(targetId)) params.append("target_id", targetId);
      });
      return params instanceof URLSearchParams ? params : new URLSearchParams();
    }
    function serverFilterKey(projectId, summary) {
      const params = serverFilterParams(projectId, summary);
      params.sort?.();
      return params.toString();
    }
    async function load(projectId, summary, options = {}) {
      const normalizedProjectId = String(projectId || ctx.selectedProjectId?.() || "");
      if (!normalizedProjectId) return null;
      const state = page(normalizedProjectId);
      if (Object.prototype.hasOwnProperty.call(options, "offset")) {
        state.offset = Math.max(0, Number(options.offset || 0));
      }
      state.limit = Math.max(1, Math.min(Number(options.limit || pageLimit), 200));
      const params = serverFilterParams(normalizedProjectId, summary);
      params.set("limit", String(state.limit));
      params.set("offset", String(state.offset));
      state.filterKey = serverFilterKey(normalizedProjectId, summary);
      state.loading = true;
      state.error = "";
      try {
        const resp = await ctx.apiFetch(`/projects/${encodeURIComponent(normalizedProjectId)}/artifacts?${params.toString()}`, {
          cache: "no-store"
        });
        if (!resp.ok) throw await ctx.projectResponseError(resp, "Could not load project artifacts.");
        const data = await resp.json();
        state.artifacts = Array.isArray(data.artifacts) ? data.artifacts : [];
        state.total = Number(data.total || 0);
        state.limit = Number(data.limit || state.limit);
        state.offset = Number(data.offset || 0);
        state.runCounts = data.run_counts && typeof data.run_counts === "object" ? data.run_counts : {};
        let fallbackArtifacts = summary && Array.isArray(summary.artifacts) ? summary.artifacts : [];
        if (state.filterKey && typeof ctx.filteredProjectArtifacts === "function") {
          const filteredFallback = ctx.filteredProjectArtifacts(normalizedProjectId, summary);
          fallbackArtifacts = Array.isArray(filteredFallback) ? filteredFallback : fallbackArtifacts;
        }
        if (!state.artifacts.length && fallbackArtifacts.length) {
          state.artifacts = fallbackArtifacts.slice(state.offset, state.offset + state.limit);
          state.total = fallbackArtifacts.length;
          const runCounts = {};
          fallbackArtifacts.forEach((artifact) => {
            const runId = String(artifact && artifact.run_id || "");
            runCounts[runId] = Number(runCounts[runId] || 0) + 1;
          });
          state.runCounts = runCounts;
        }
        state.loaded = true;
        return state;
      } catch (err) {
        state.error = err && err.message ? err.message : "Could not load project artifacts.";
        ctx.setProjectWorkspaceMessage?.(state.error, { error: true });
        if (typeof ctx.logClientError === "function") ctx.logClientError("failed to load project artifacts", err);
        return state;
      } finally {
        state.loading = false;
        if (!options.skipFinalRender) {
          ctx.renderProjectExplorer?.();
          if (ctx.mobileView?.() === "detail") ctx.renderProjectMobileDetail?.();
        }
      }
    }
    async function loadAll(projectId, summary) {
      const normalizedProjectId = String(projectId || ctx.selectedProjectId?.() || "");
      if (!normalizedProjectId) return [];
      if (allArtifacts.has(normalizedProjectId)) return allArtifacts.get(normalizedProjectId);
      const collected = [];
      let offset = 0;
      let total = 0;
      do {
        const params = new URLSearchParams({ limit: "200", offset: String(offset) });
        const resp = await ctx.apiFetch(`/projects/${encodeURIComponent(normalizedProjectId)}/artifacts?${params.toString()}`, {
          cache: "no-store"
        });
        if (!resp.ok) throw await ctx.projectResponseError(resp, "Could not load project artifacts.");
        const data = await resp.json();
        const rows = Array.isArray(data.artifacts) ? data.artifacts : [];
        collected.push(...rows);
        total = Number(data.total || collected.length);
        offset += rows.length;
        if (!rows.length) break;
      } while (collected.length < total);
      if (!collected.length && summary && Array.isArray(summary.artifacts)) {
        collected.push(...summary.artifacts);
      }
      allArtifacts.set(normalizedProjectId, collected);
      return collected;
    }
    function renderPagination(projectId, total, position = "bottom") {
      const state = page(projectId);
      const offset = Number(state.offset || 0);
      const limit = Math.max(1, Number(state.limit || pageLimit));
      const loading = !!state.loading;
      if (total <= limit && offset === 0) return null;
      const wrap = document.createElement("div");
      wrap.className = "project-workspace-pagination project-artifact-pagination";
      wrap.dataset.projectArtifactsPagerPosition = position;
      const start = total ? offset + 1 : 0;
      const end = Math.min(total, offset + limit);
      const summary = document.createElement("div");
      summary.className = "project-workspace-pagination-summary";
      summary.textContent = `${start.toLocaleString()}-${end.toLocaleString()} of ${total.toLocaleString()} artifacts`;
      const controls = document.createElement("div");
      controls.className = "project-workspace-pagination-controls";
      const prev = ctx.makeProjectButton("Previous", "noop", projectId);
      prev.dataset.projectArtifactsPage = "prev";
      prev.dataset.projectArtifactsPagerPosition = position;
      prev.disabled = loading || offset <= 0;
      const status2 = document.createElement("span");
      status2.className = "project-workspace-pagination-status";
      status2.textContent = loading ? "Loading..." : `Page ${Math.floor(offset / limit) + 1}`;
      const next = ctx.makeProjectButton("Next", "noop", projectId);
      next.dataset.projectArtifactsPage = "next";
      next.dataset.projectArtifactsPagerPosition = position;
      next.disabled = loading || offset + limit >= total;
      controls.append(prev, status2, next);
      wrap.append(summary, controls);
      return wrap;
    }
    async function preview(projectId, artifactId) {
      const resp = await ctx.apiFetch(
        `/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifactId)}/preview`,
        { cache: "no-store" }
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.error || "Unable to preview artifact.");
      const artifact = data.artifact || {};
      const showViewer = typeof showWorkspaceViewer === "function" ? showWorkspaceViewer : null;
      if (!showViewer) throw new Error("File preview is not available.");
      showViewer(
        artifact.workspace_path || "artifact",
        data.text || "",
        { size: artifact.current_byte_size ?? artifact.byte_size ?? null, elevated: true }
      );
    }
    async function download(projectId, artifactId, artifactPath = "") {
      const resp = await ctx.apiFetch(
        `/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifactId)}/download-ticket`,
        { method: "POST", cache: "no-store" }
      );
      if (!resp.ok) {
        const data2 = await resp.json().catch(() => ({}));
        throw new Error(data2.error || "Unable to download artifact.");
      }
      const data = await resp.json().catch(() => ({}));
      ctx.downloadUrlAsAttachment(
        data.url,
        downloadName(artifactPath, artifactId || "artifact"),
        "Artifact download started."
      );
    }
    function renderArtifacts(container, projectId, summary) {
      const totalArtifacts = Number(summary?.counts?.artifacts || 0);
      const filterActive = ctx.projectTargetFilterActive(projectId, summary);
      if (filterActive && !ctx.projectFindingsLoaded(projectId)) {
        container.appendChild(ctx.emptyProjectPanel("Loading target associations..."));
        return;
      }
      const state = page(projectId);
      const filterKey = serverFilterKey(projectId, summary);
      if ((!state.loaded || state.filterKey !== filterKey) && !state.loading) {
        load(projectId, summary, { offset: state.filterKey === filterKey ? state.offset : 0 }).catch(() => {
        });
      }
      const pageArtifacts = state.artifacts || [];
      if (!totalArtifacts) {
        container.appendChild(ctx.emptyProjectPanel("No run artifacts have been captured for this project yet."));
        return;
      }
      if (state.loading && !pageArtifacts.length) {
        container.appendChild(ctx.emptyProjectPanel("Loading project artifacts..."));
        return;
      }
      if (state.error && !pageArtifacts.length) {
        container.appendChild(ctx.emptyProjectPanel(state.error));
        return;
      }
      if (!state.total) {
        container.appendChild(ctx.emptyProjectPanel("No artifacts match the selected targets."));
        return;
      }
      const artifactTotalsByRun = new Map(Object.entries(state.runCounts || {}));
      const topPager = renderPagination(projectId, state.total, "top");
      if (topPager) container.appendChild(topPager);
      ctx.groupBy(pageArtifacts, (artifact) => artifact.run_id).forEach((groupItems, runId) => {
        const group = document.createElement("section");
        group.className = "project-explorer-group project-artifacts-group";
        const run = ctx.projectRunById(summary, runId);
        const command = String(run?.command || "").trim();
        const shortId = ctx.shortProjectRunId(runId);
        const collapsed = groupCollapsed(projectId, runId);
        group.classList.toggle("is-collapsed", collapsed);
        const title = document.createElement("button");
        title.type = "button";
        title.className = "toggle-btn project-explorer-group-toggle";
        title.dataset.projectArtifactGroupToggle = "1";
        title.dataset.projectId = projectId;
        title.dataset.projectArtifactGroup = String(runId || "");
        title.setAttribute("aria-expanded", collapsed ? "false" : "true");
        ctx.bindProjectRuntimePressable(title);
        const caret = document.createElement("span");
        caret.className = "project-explorer-group-caret";
        caret.setAttribute("aria-hidden", "true");
        caret.textContent = ctx.groupCaret || "";
        const label = document.createElement("span");
        label.className = "project-explorer-group-title";
        label.textContent = `${command || "Run"}${shortId ? ` (${shortId})` : ""}`;
        const count = document.createElement("span");
        count.className = "project-explorer-group-count";
        const totalForRun = Number(artifactTotalsByRun.get(String(runId || "")) || groupItems.length);
        const visibleCountText = groupItems.length === totalForRun ? `${groupItems.length}` : `${groupItems.length} of ${totalForRun}`;
        count.textContent = `${visibleCountText} artifact${totalForRun === 1 ? "" : "s"}`;
        title.append(caret, label, count);
        group.appendChild(title);
        const body = document.createElement("div");
        body.className = "project-explorer-group-body";
        body.hidden = collapsed;
        groupItems.forEach((artifact) => {
          body.appendChild(ctx.projectItemRow({
            title: artifact.display_name || artifact.workspace_path,
            meta: artifact.workspace_path,
            detail: detail(artifact),
            chips: ctx.entityMetadataChips(artifact),
            accessory: accessory(projectId, artifact)
          }));
        });
        group.appendChild(body);
        container.appendChild(group);
      });
      const bottomPager = renderPagination(projectId, state.total, "bottom");
      if (bottomPager) container.appendChild(bottomPager);
    }
    return {
      page,
      setPageOffset,
      invalidate,
      groupKey,
      groupCollapsed,
      serverFilterParams,
      serverFilterKey,
      items,
      pagedItems,
      load,
      loadAll,
      filesEnabled,
      artifactsVisible,
      status,
      statusLabel,
      accessory,
      detail,
      detailLines,
      downloadName,
      preview,
      download,
      renderArtifacts
    };
  }
  const DarklabProjectArtifacts = {
    createProjectArtifactsController
  };
  exportedDarklabProjectArtifacts = DarklabProjectArtifacts;
})(globalThis);
export {
  exportedDarklabProjectArtifacts as DarklabProjectArtifacts
};
