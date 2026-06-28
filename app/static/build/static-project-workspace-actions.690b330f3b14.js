import {
  showConfirm
} from "./static-chunk-4m44pm74.0a8001fa1d52.js";
import "./static-chunk-2bgb52uq.a327269283bb.js";
import "./static-chunk-yo5cjr7d.b86e0c93eff0.js";

// app/static/js/features/projects/project_workspace_actions.js
var exportedDarklabProjectWorkspaceActions = null;
(function projectWorkspaceActionsModule(global) {
  "use strict";
  function createProjectWorkspaceActionsController(context) {
    const ctx = context || {};
    function projectShowConfirm() {
      return typeof ctx.showConfirm === "function" ? ctx.showConfirm : typeof showConfirm !== "undefined" && showConfirm || null;
    }
    async function syncEntityLabels(entityType, entityId, nextLabels) {
      await ctx.EntityMetadataClient.syncEntityLabels(entityType, entityId, nextLabels, {
        request: ctx.projectWorkspaceRequest
      });
    }
    async function syncEntityNote(entityType, entityId, body) {
      await ctx.EntityMetadataClient.syncEntityNote(entityType, entityId, body, {
        request: ctx.projectWorkspaceRequest
      });
    }
    async function previewRunEntitiesForLink(projectId, runIds) {
      const normalizedProjectId = String(projectId || "").trim();
      const ids = (Array.isArray(runIds) ? runIds : [runIds]).map((runId) => String(runId || "").trim()).filter(Boolean);
      if (!normalizedProjectId || !ids.length) return null;
      const resp = await ctx.apiFetch(`/projects/${encodeURIComponent(normalizedProjectId)}/links/run-entities/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_ids: ids })
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      return data && data.preview ? data.preview : null;
    }
    function runEntityLinkOption(preview) {
      const count = Number(preview && preview.linkable || 0);
      if (count <= 0) return null;
      const wrap = document.createElement("div");
      wrap.className = "project-run-entities-option";
      const label = document.createElement("label");
      label.className = "form-check";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = false;
      const text = document.createElement("span");
      const runCount = Number(preview && preview.run_count || 0);
      text.textContent = runCount > 1 ? `Also add ${count.toLocaleString()} Atlas ${count === 1 ? "entity" : "entities"} found in these runs` : `Also add ${count.toLocaleString()} Atlas ${count === 1 ? "entity" : "entities"} found in this run`;
      label.append(checkbox, text);
      wrap.appendChild(label);
      return { wrap, checkbox };
    }
    async function confirmRunLink(projectId, runIds, label) {
      const confirmFn = projectShowConfirm();
      if (!confirmFn) return { includeEntities: false };
      let option = null;
      try {
        option = runEntityLinkOption(await previewRunEntitiesForLink(projectId, runIds));
      } catch (_) {
        option = null;
      }
      const choice = await confirmFn({
        body: label,
        content: option ? option.wrap : null,
        tone: null,
        actions: [
          { id: "cancel", label: "Cancel", role: "cancel" },
          { id: "add", label: "Add to project", role: "primary" }
        ]
      });
      if (choice !== "add") return null;
      return { includeEntities: !!(option && option.checkbox.checked) };
    }
    async function linkLastRunToProject(projectId, summary) {
      const normalizedProjectId = String(projectId || ctx.selectedProjectId?.() || "").trim();
      if (!normalizedProjectId) throw new Error("Select or create a project before linking runs.");
      const linkedRunIds = new Set(ctx.projectRunItems(summary).map((run2) => String(run2 && run2.id || "")).filter(Boolean));
      const resp = await ctx.apiFetch("/history?type=runs&page_size=25", { cache: "no-store" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      const candidates = Array.isArray(data.runs) ? data.runs : Array.isArray(data.items) ? data.items : [];
      const run = candidates.find((item) => {
        const runId = String(item && item.id || "");
        return runId && !linkedRunIds.has(runId) && (!item.type || item.type === "run");
      });
      if (!run) throw new Error("No unlinked recent run found.");
      const confirmed = await confirmRunLink(normalizedProjectId, [String(run.id || "")], "Add the last run to this project?");
      if (!confirmed) return;
      const linkResp = await ctx.projectWorkspaceRequest(`/projects/${encodeURIComponent(normalizedProjectId)}/links`, {
        method: "POST",
        body: JSON.stringify({
          entity_type: "run",
          entity_id: String(run.id || ""),
          source: "manual",
          ...confirmed.includeEntities ? { include_entities: true } : {}
        })
      });
      await ctx.refreshProjectWorkspace();
      const addedEntities = Number(linkResp && linkResp.linked_entities && linkResp.linked_entities.added || 0);
      ctx.setProjectWorkspaceMessage(addedEntities ? `Last run and ${addedEntities.toLocaleString()} ${addedEntities === 1 ? "entity" : "entities"} linked to this project.` : "Last run linked to this project.");
    }
    async function confirmDestructive({ body, actionLabel, actionId, note }) {
      const confirmFn = projectShowConfirm();
      if (!confirmFn) {
        throw new Error("Project destructive confirmations require showConfirm.");
      }
      const choice = await confirmFn({
        body: note ? { text: body, note } : body,
        tone: "danger",
        actions: [
          { id: "cancel", label: "Cancel", role: "cancel" },
          { id: actionId, label: actionLabel, role: "destructive" }
        ]
      });
      return choice === actionId;
    }
    function confirmTargetDelete(targetValue) {
      const label = String(targetValue || "this target");
      return confirmDestructive({
        body: `Remove target ${label}?`,
        actionLabel: "Remove",
        actionId: "remove"
      });
    }
    function confirmRunUnlink(runCommand) {
      const label = String(runCommand || "this run");
      return confirmDestructive({
        body: `Remove run from project: ${label}?`,
        actionLabel: "Remove",
        actionId: "remove"
      });
    }
    function confirmPackageDelete(packageName) {
      const label = String(packageName || "this package");
      return confirmDestructive({
        body: `Delete package: ${label}?`,
        actionLabel: "Delete",
        actionId: "delete"
      });
    }
    function confirmProjectDelete(projectName) {
      const label = String(projectName || "this project");
      return confirmDestructive({
        body: `Delete project: ${label}?`,
        note: "This removes the project, its targets, packages, and project links. Source runs and saved history remain.",
        actionLabel: "Delete",
        actionId: "delete"
      });
    }
    return {
      confirmDestructive,
      confirmPackageDelete,
      confirmProjectDelete,
      confirmRunLink,
      confirmRunUnlink,
      confirmTargetDelete,
      linkLastRunToProject,
      previewRunEntitiesForLink,
      syncEntityLabels,
      syncEntityNote
    };
  }
  const DarklabProjectWorkspaceActions = { createProjectWorkspaceActionsController };
  exportedDarklabProjectWorkspaceActions = DarklabProjectWorkspaceActions;
})(globalThis);
export {
  exportedDarklabProjectWorkspaceActions as DarklabProjectWorkspaceActions
};
