import {
  exportedOpenAtlas
} from "./static-chunk-rykdigcy.0e068a74cb59.js";
import {
  exportedOpenFindingsBoard
} from "./static-chunk-u3qyihdg.3b5b31bc2ecc.js";
import "./static-chunk-wkdqs5l5.75c18d0d56e7.js";
import "./static-chunk-juqfoveq.8c944162f0c1.js";
import "./static-chunk-255aiqlc.6801a1b0602e.js";
import "./static-chunk-72wip37o.8b07cec02a1a.js";
import "./static-chunk-dil5yyjg.6d28df9092db.js";
import {
  DarklabFindingTriageEditor
} from "./static-chunk-xcutwwwr.d3961e123254.js";
import {
  restoreHistoryRunIntoTab
} from "./static-chunk-434ox2qu.96ed0dc8cf79.js";
import "./static-chunk-3jpzlov4.47e7ebc68e55.js";
import "./static-chunk-iimv3vvo.e054c6ada14d.js";
import "./static-chunk-ylgcpl7n.752d37b456dc.js";
import {
  activeTeamScopeCan,
  teamScopeDeniedMessage
} from "./static-chunk-xefchp2g.f0a8d56ae694.js";
import "./static-chunk-poi5czx6.3f5c94749765.js";
import "./static-chunk-lxs2zdd2.87dc9e4c1317.js";
import "./static-chunk-fik64llj.1291b1f4f79b.js";
import "./static-chunk-yu6ty7m2.96c3ee208a44.js";
import "./static-chunk-sgyzdmxn.7d1842f12a94.js";
import "./static-chunk-tym5o2af.a748583ae389.js";
import "./static-chunk-i34eiczq.4bb950c346dc.js";
import "./static-chunk-4nkiwrht.8176cfb2b3d4.js";
import "./static-chunk-m4e6ivjw.074a5c89d41e.js";
import "./static-chunk-6ep7jfeg.e8819f5c9afc.js";
import "./static-chunk-y6zchygr.f5ddd7fe938a.js";

// app/static/js/features/projects/project_workspace_events.js
var exportedDarklabProjectWorkspaceEvents = null;
(function projectWorkspaceEventsModule(global) {
  "use strict";
  function createProjectWorkspaceEventsController(context) {
    const ctx = context || {};
    function selectedProjectId() {
      return String(ctx.selectedProjectId?.() || "");
    }
    function workspaceTab() {
      return String(ctx.workspaceTab?.() || "details");
    }
    function mobileView() {
      return String(ctx.mobileView?.() || "list");
    }
    function projectRows() {
      const rows = ctx.projectRows?.();
      return Array.isArray(rows) ? rows : [];
    }
    function selectedEntityIds() {
      return ctx.selectedEntityIds?.() || /* @__PURE__ */ new Set();
    }
    function selectedFindingIds() {
      return ctx.selectedFindingIds?.() || /* @__PURE__ */ new Set();
    }
    function activeTeamScopeCan2(capability) {
      const can = typeof activeTeamScopeCan !== "undefined" && activeTeamScopeCan || null;
      return typeof can === "function" ? can(capability) : true;
    }
    function teamScopeDeniedMessage2(action) {
      const denied = typeof teamScopeDeniedMessage !== "undefined" && teamScopeDeniedMessage || null;
      return typeof denied === "function" ? denied(action) : `View-only team members can't ${action}. Switch to Personal or ask for operator access.`;
    }
    function denyTeamScopeAction(action) {
      ctx.setProjectWorkspaceMessage(teamScopeDeniedMessage2(action), { error: true });
    }
    function projectFromRowsOrSummary(projectId) {
      const summary = ctx.projectSummary?.(projectId);
      return summary && summary.project && typeof summary.project === "object" ? summary.project : projectRows().find((item) => String(item.id || "") === String(projectId || ""));
    }
    function projectFindingById(projectId, findingId) {
      const normalizedFindingId = String(findingId || "");
      if (!normalizedFindingId) return null;
      const summary = ctx.projectSummary?.(projectId);
      const lists = [
        ctx.projectFindingItems?.(projectId),
        ctx.filteredProjectFindings?.(projectId, summary)
      ];
      for (const list of lists) {
        if (!Array.isArray(list)) continue;
        const finding = list.find((item) => String(item && item.id || "") === normalizedFindingId);
        if (finding) return finding;
      }
      return null;
    }
    function restoreHistoryRun() {
      if (typeof ctx.restoreHistoryRunIntoTab === "function") return ctx.restoreHistoryRunIntoTab;
      if (typeof ctx.restoreHistoryRun === "function") return ctx.restoreHistoryRun;
      return typeof restoreHistoryRunIntoTab === "function" ? restoreHistoryRunIntoTab : null;
    }
    function pagerDescriptor(button) {
      const configs = [
        {
          pageDataset: "projectFindingsPage",
          positionDataset: "projectFindingsPagerPosition",
          pageAttr: "data-project-findings-page",
          positionAttr: "data-project-findings-pager-position"
        },
        {
          pageDataset: "projectRunsPage",
          positionDataset: "projectRunsPagerPosition",
          pageAttr: "data-project-runs-page",
          positionAttr: "data-project-runs-pager-position"
        },
        {
          pageDataset: "projectEntitiesPage",
          positionDataset: "projectEntitiesPagerPosition",
          pageAttr: "data-project-entities-page",
          positionAttr: "data-project-entities-pager-position"
        },
        {
          pageDataset: "projectArtifactsPage",
          positionDataset: "projectArtifactsPagerPosition",
          pageAttr: "data-project-artifacts-page",
          positionAttr: "data-project-artifacts-pager-position"
        },
        {
          pageDataset: "projectTargetsPage",
          positionDataset: "projectTargetsPagerPosition",
          pageAttr: "data-project-targets-page",
          positionAttr: "data-project-targets-pager-position"
        }
      ];
      return configs.find((config) => button?.dataset?.[config.pageDataset]) || null;
    }
    function preservePagerPosition(button, render) {
      const scrollBody = mobileView() === "detail" ? ctx.projectMobileDetailBody : ctx.projectExplorerBody;
      const descriptor = pagerDescriptor(button);
      const page = descriptor ? String(button?.dataset?.[descriptor.pageDataset] || "") : "";
      const pagerPosition = descriptor ? String(button?.dataset?.[descriptor.positionDataset] || "") : "";
      const positionSelector = descriptor && pagerPosition ? `[${descriptor.positionAttr}="${pagerPosition}"]` : "";
      const selector = descriptor && page ? `[${descriptor.pageAttr}="${page}"]${positionSelector}` : "";
      const anchor = button?.isConnected ? button : selector ? scrollBody?.querySelector(selector) : null;
      const beforeTop = anchor?.getBoundingClientRect?.().top;
      render();
      if (scrollBody && pagerPosition === "bottom") {
        scrollBody.scrollTop = Math.max(0, scrollBody.scrollHeight - scrollBody.clientHeight);
        return;
      }
      if (!scrollBody || !Number.isFinite(beforeTop) || !page) return;
      const nextButton = scrollBody.querySelector(selector);
      const afterTop = nextButton?.getBoundingClientRect?.().top;
      if (Number.isFinite(afterTop)) {
        scrollBody.scrollTop += afterTop - beforeTop;
      }
    }
    function projectPageOffset(pagination, direction) {
      const limit = Math.max(1, Number(pagination?.limit || 50));
      const offset = Math.max(0, Number(pagination?.offset || 0));
      const total = Math.max(0, Number(pagination?.total || 0));
      return String(direction || "") === "prev" ? Math.max(0, offset - limit) : Math.min(offset + limit, Math.max(0, total - 1));
    }
    function renderProjectViews() {
      ctx.renderProjectExplorer();
      if (mobileView() === "detail") ctx.renderProjectMobileDetail();
    }
    async function runProjectPager(button, loadPage) {
      if (!button || button.disabled || typeof loadPage !== "function") return;
      preservePagerPosition(button, renderProjectViews);
      await loadPage();
      preservePagerPosition(button, renderProjectViews);
    }
    async function handleInput(event) {
      if (ctx.entitiesController?.().handleAutoPromoteInput(event)) return;
      const reportController = ctx.reportController?.();
      if (reportController && reportController.handleInput(event)) return;
      const packagesController = ctx.packagesController?.();
      packagesController?.handleInput(event);
    }
    async function handleChange(event) {
      if (ctx.entitiesController?.().handleAutoPromoteChange(event)) return;
      const monitoringController = ctx.monitoringController?.();
      if (monitoringController && monitoringController.handleChange(event)) return;
      const reportController = ctx.reportController?.();
      if (reportController && reportController.handleChange(event)) return;
      const packagesController = ctx.packagesController?.();
      if (packagesController && packagesController.handleChange(event)) return;
      const findingViewModeControl = event.target.closest?.("[data-project-finding-view-mode]");
      if (findingViewModeControl) {
        event.preventDefault();
        event.stopPropagation();
        const mode = String(findingViewModeControl.dataset.projectFindingViewMode || "list");
        ctx.setFindingViewMode(mode);
        ctx.renderProjectExplorer();
        return;
      }
      const compareModeControl = event.target.closest?.("[data-project-compare-mode]");
      if (compareModeControl) {
        event.stopPropagation();
        ctx.syncProjectRunCompareMode(compareModeControl.closest(".project-run-compare-controls"));
        return;
      }
      const compareControl = event.target.closest?.('[data-project-compare-target], [data-project-compare-run="left"]');
      if (compareControl) {
        const controls = compareControl.closest(".project-run-compare-controls");
        if (String(controls?.querySelector("[data-project-compare-mode]")?.value || "run") === "baseline") {
          ctx.avoidProjectRunCompareLabelSelfTarget(
            controls,
            String(controls?.querySelector("[data-project-compare-target]")?.value || "")
          );
        }
        return;
      }
      const sortControl = event.target.closest?.("[data-project-finding-sort]");
      if (sortControl) {
        event.stopPropagation();
        const projectId2 = String(sortControl.dataset.projectId || selectedProjectId() || "");
        if (!projectId2) return;
        ctx.filtersController?.().setFindingSort(projectId2, String(sortControl.value || "run"));
        ctx.renderProjectExplorer();
        return;
      }
      const targetFilterControl = event.target.closest?.("[data-project-target-filter-option]");
      if (targetFilterControl) {
        event.stopPropagation();
        const projectId2 = String(targetFilterControl.dataset.projectId || selectedProjectId() || "");
        const targetId = String(targetFilterControl.value || "");
        if (!projectId2 || !targetId) return;
        const filters = ctx.projectTargetFilterSet(projectId2);
        if (targetFilterControl.checked) filters.add(targetId);
        else filters.delete(targetId);
        ctx.renderProjectExplorer();
        return;
      }
      const runFilterControl = event.target.closest?.("[data-project-run-filter-option]");
      if (runFilterControl) {
        event.stopPropagation();
        const projectId2 = String(runFilterControl.dataset.projectId || selectedProjectId() || "");
        const runId = String(runFilterControl.value || "");
        if (!projectId2 || !runId) return;
        const filters = ctx.projectRunFilterSet(projectId2);
        if (runFilterControl.checked) filters.add(runId);
        else filters.delete(runId);
        ctx.renderProjectExplorer();
        return;
      }
      const statusFilterControl = event.target.closest?.("[data-project-finding-status-filter-option]");
      if (statusFilterControl) {
        event.stopPropagation();
        const projectId2 = String(statusFilterControl.dataset.projectId || selectedProjectId() || "");
        const status = String(statusFilterControl.value || "");
        if (!projectId2 || !status) return;
        const filters = ctx.projectFindingStatusFilterSet(projectId2);
        if (statusFilterControl.checked) filters.add(status);
        else filters.delete(status);
        ctx.renderProjectExplorer();
        return;
      }
      const commandFilterControl = event.target.closest?.("[data-project-finding-command-filter-option]");
      if (commandFilterControl) {
        event.stopPropagation();
        const projectId2 = String(commandFilterControl.dataset.projectId || selectedProjectId() || "");
        const commandRoot = String(commandFilterControl.value || "").trim();
        if (!projectId2 || !commandRoot) return;
        const filters = ctx.projectFindingCommandFilterSet(projectId2);
        if (commandFilterControl.checked) filters.add(commandRoot);
        else filters.delete(commandRoot);
        ctx.renderProjectExplorer();
        return;
      }
      const severityFilterControl = event.target.closest?.("[data-project-finding-severity-filter-option]");
      if (severityFilterControl) {
        event.stopPropagation();
        const projectId2 = String(severityFilterControl.dataset.projectId || selectedProjectId() || "");
        const severity = String(severityFilterControl.value || "").trim();
        if (!projectId2 || !severity) return;
        const filters = ctx.projectFindingSeverityFilterSet(projectId2);
        if (severityFilterControl.checked) filters.add(severity);
        else filters.delete(severity);
        ctx.renderProjectExplorer();
        return;
      }
      const scopeFilterControl = event.target.closest?.("[data-project-finding-scope-filter-option]");
      if (scopeFilterControl) {
        event.stopPropagation();
        const projectId2 = String(scopeFilterControl.dataset.projectId || selectedProjectId() || "");
        const scope = String(scopeFilterControl.value || "").trim();
        if (!projectId2 || !scope) return;
        const filters = ctx.projectFindingScopeFilterSet(projectId2);
        if (scopeFilterControl.checked) filters.add(scope);
        else filters.delete(scope);
        ctx.renderProjectExplorer();
        return;
      }
      const labelFilterControl = event.target.closest?.("[data-project-finding-label-filter-option]");
      if (labelFilterControl) {
        event.stopPropagation();
        const projectId2 = String(labelFilterControl.dataset.projectId || selectedProjectId() || "");
        const labelValue = String(labelFilterControl.value || "").trim();
        if (!projectId2 || !labelValue) return;
        const filters = ctx.projectFindingLabelFilterSet(projectId2);
        if (labelFilterControl.checked) filters.add(labelValue);
        else filters.delete(labelValue);
        ctx.renderProjectExplorer();
        return;
      }
      const noteStateControl = event.target.closest?.("[data-project-finding-note-state]");
      if (noteStateControl) {
        event.stopPropagation();
        const projectId2 = String(noteStateControl.dataset.projectId || selectedProjectId() || "");
        if (!projectId2) return;
        ctx.filtersController?.().setFindingNoteState(projectId2, noteStateControl.value);
        ctx.renderProjectExplorer();
        return;
      }
      const orphanControl = event.target.closest?.("[data-project-finding-orphan]");
      if (orphanControl) {
        event.stopPropagation();
        const projectId2 = String(orphanControl.dataset.projectId || selectedProjectId() || "");
        if (!projectId2) return;
        ctx.filtersController?.().setFindingOrphanFilter(projectId2, orphanControl.value);
        ctx.renderProjectExplorer();
        return;
      }
      const bulkReview = event.target.closest?.("[data-project-finding-bulk-review]");
      if (bulkReview) {
        event.stopPropagation();
        const projectId2 = String(bulkReview.dataset.projectId || selectedProjectId() || "");
        const reviewState2 = String(bulkReview.value || "");
        if (!projectId2 || !reviewState2 || !selectedFindingIds().size) return;
        if (!activeTeamScopeCan2("triage_findings")) {
          denyTeamScopeAction("triage team findings");
          return;
        }
        const findingIds = [...selectedFindingIds()];
        try {
          const resp = await ctx.projectWorkspaceRequest(`/projects/${encodeURIComponent(projectId2)}/findings/review`, {
            method: "POST",
            body: JSON.stringify({ finding_ids: findingIds, review_state: reviewState2 })
          });
          const result = await resp.json();
          const updatedIds = Array.isArray(result?.results) ? result.results.filter((item) => item && item.status === "updated").map((item) => String(item.finding_id || "")) : findingIds;
          updatedIds.forEach((findingId2) => ctx.setCachedFindingReviewState(projectId2, findingId2, reviewState2));
          const activityController = ctx.activityController?.();
          activityController?.invalidate?.(projectId2);
          selectedFindingIds().clear();
          ctx.setFindingSelectMode(false);
          ctx.renderProjectExplorer();
          const notFound = Number(result?.counts?.not_found || 0);
          ctx.setProjectWorkspaceMessage(
            notFound ? `Finding review states updated; ${notFound} stale ${notFound === 1 ? "selection was" : "selections were"} skipped.` : "Finding review states updated."
          );
        } catch (err) {
          ctx.setProjectWorkspaceMessage(err.message || "Could not update finding review states.", { error: true });
        }
        return;
      }
      const control = event.target.closest?.("[data-project-review-state]");
      if (!control) return;
      event.preventDefault();
      event.stopPropagation();
      const projectId = String(control.dataset.projectId || "");
      const findingId = String(control.dataset.findingId || "");
      const reviewState = String(control.value || "new");
      const previousReviewState = String(control.dataset.previousReviewState || "new");
      ctx.setProjectWorkspaceMessage("");
      if (!activeTeamScopeCan2("triage_findings")) {
        control.value = previousReviewState;
        denyTeamScopeAction("triage team findings");
        return;
      }
      ctx.setCachedFindingReviewState(projectId, findingId, reviewState);
      ctx.renderProjectExplorer();
      if (mobileView() === "detail" && workspaceTab() === "findings" && selectedProjectId() === projectId) {
        ctx.renderProjectMobileDetail();
      }
      try {
        const resp = await ctx.projectWorkspaceRequest(`/projects/${encodeURIComponent(projectId)}/findings/review`, {
          method: "POST",
          body: JSON.stringify({ finding_ids: [findingId], review_state: reviewState })
        });
        const result = await resp.json();
        const updated = Number(result?.counts?.updated || 0);
        if (!updated) throw new Error("Finding was no longer available in this project.");
        const activityController = ctx.activityController?.();
        activityController?.invalidate?.(projectId);
        control.dataset.previousReviewState = reviewState;
      } catch (err) {
        ctx.setCachedFindingReviewState(projectId, findingId, previousReviewState);
        ctx.renderProjectExplorer();
        if (mobileView() === "detail" && workspaceTab() === "findings" && selectedProjectId() === projectId) {
          ctx.renderProjectMobileDetail();
        }
        ctx.setProjectWorkspaceMessage(err.message || "Could not update finding review state.", { error: true });
      }
    }
    async function handleDocumentPickerClick(event) {
      await ctx.entitiesController?.().handlePickerClick(event);
    }
    function handleDocumentPickerInput(event) {
      ctx.entitiesController?.().handlePickerInput(event);
    }
    function handleDocumentPickerChange(event) {
      ctx.entitiesController?.().handlePickerChange(event);
    }
    function handleDocumentFilterMenuClick(event) {
      if (!ctx.isProjectWorkspaceOpen()) return;
      const menu = event.target.closest?.(".project-target-filter-menu");
      if (menu && ctx.projectWorkspaceModal?.contains(menu)) {
        ctx.closeProjectFilterMenus(menu);
        return;
      }
      ctx.closeProjectFilterMenus();
    }
    function handlePointerDown(event) {
      const tabBtn = event.target.closest?.("[data-project-tab]");
      if (!tabBtn) return;
      event.preventDefault();
    }
    async function handleClick(event) {
      const mobileDetailTab = event.target.closest?.("[data-project-mobile-detail-tab]");
      if (mobileDetailTab) {
        event.preventDefault();
        event.stopPropagation();
        await ctx.flushProjectNotesAutosave();
        const nextTab = String(mobileDetailTab.dataset.projectMobileDetailTab || "details");
        if (workspaceTab() !== nextTab && ctx.projectMobileDetailBody) ctx.projectMobileDetailBody.scrollTop = 0;
        ctx.setWorkspaceTab(nextTab);
        ctx.closeProjectTargetEditor();
        ctx.closeProjectEntityEditor();
        ctx.setProjectWorkspaceMessage("");
        ctx.renderProjectMobileDetail();
        return;
      }
      const mobileTab = event.target.closest?.("[data-project-mobile-tab]");
      if (mobileTab) {
        event.preventDefault();
        event.stopPropagation();
        await ctx.flushProjectNotesAutosave();
        ctx.selectProjectFromMobile(mobileTab.dataset.projectId || "", mobileTab.dataset.projectMobileTab || "details");
        return;
      }
      const mobileAction = event.target.closest?.("[data-project-mobile-action]");
      if (mobileAction) {
        event.preventDefault();
        event.stopPropagation();
        const mobileProjectId = String(mobileAction.dataset.projectId || "");
        const action = String(mobileAction.dataset.projectMobileAction || "");
        if (action === "new-project") {
          ctx.setProjectWorkspaceMessage("");
          ctx.setProjectMobileCreateOpen(true, { focus: true });
          return;
        }
        if (action === "cancel-create") {
          ctx.setProjectWorkspaceMessage("");
          ctx.setProjectMobileCreateOpen(false);
          return;
        }
        if (action === "back-to-list") {
          await ctx.flushProjectNotesAutosave();
          ctx.setProjectWorkspaceMessage("");
          ctx.setProjectMobileView("list");
          ctx.renderProjectMobile();
          return;
        }
        if (action === "retry") {
          ctx.refreshProjectWorkspace().catch(() => {
          });
          return;
        }
        if (action === "toggle-archived") {
          ctx.toggleMobileArchivedOpen();
          ctx.renderProjectMobile();
          return;
        }
        if (action === "open-project") {
          await ctx.flushProjectNotesAutosave();
          ctx.selectProjectFromMobile(mobileProjectId);
          return;
        }
        if (action === "project-menu") {
          const project = projectRows().find((item) => String(item.id || "") === mobileProjectId) || ctx.projectSummary?.(mobileProjectId)?.project || null;
          if (!project) return;
          ctx.openProjectMobileActionSheet(
            mobileProjectId,
            `Project actions for ${ctx.projectDisplayName(project)}`,
            ctx.projectMobileProjectActions(project),
            mobileAction
          );
          return;
        }
        if (action === "action-sheet") {
          ctx.openProjectMobileActionSheet(
            mobileProjectId,
            mobileAction._projectMobileActionSheetLabel || "Actions",
            mobileAction._projectMobileActionSheetItems || [],
            mobileAction
          );
          return;
        }
      }
      const artifactGroupToggle = event.target.closest?.("[data-project-artifact-group-toggle]");
      if (artifactGroupToggle) {
        event.preventDefault();
        event.stopPropagation();
        const projectId = String(artifactGroupToggle.dataset.projectId || selectedProjectId() || "");
        const runId = String(artifactGroupToggle.dataset.projectArtifactGroup || "");
        ctx.toggleArtifactGroup(projectId, runId);
        if (mobileView() === "detail") ctx.renderProjectMobileDetail();
        else ctx.renderProjectExplorer();
        return;
      }
      if (await ctx.entitiesController?.().handleAutoPromoteClick(event)) return;
      const activityController = ctx.activityController?.();
      if (event.target.closest?.("[data-project-activity-action]") && activityController && await activityController.handleClick(event)) return;
      const monitoringController = ctx.monitoringController?.();
      if (event.target.closest?.("[data-project-monitoring-action]") && monitoringController && await monitoringController.handleClick(event)) return;
      const reportController = ctx.reportController?.();
      if (reportController && await reportController.handleClick(event)) return;
      if (event.target.closest?.("[data-project-review-state]")) return;
      const mobileProjectRow = event.target.closest?.(".project-mobile-row[data-project-id]");
      if (mobileProjectRow && ctx.projectMobileListView && ctx.projectMobileListView.contains(mobileProjectRow) && !event.target.closest?.("[data-project-mobile-action], [data-project-mobile-tab]")) {
        event.preventDefault();
        event.stopPropagation();
        await ctx.flushProjectNotesAutosave();
        ctx.selectProjectFromMobile(mobileProjectRow.dataset.projectId || "");
        return;
      }
      const compareModeButton = event.target.closest?.("[data-project-compare-mode-value]");
      if (compareModeButton) {
        ctx.setProjectRunCompareMode(compareModeButton, event);
        return;
      }
      const messageDismiss = event.target.closest?.("[data-project-message-dismiss]");
      if (messageDismiss) {
        event.preventDefault();
        event.stopPropagation();
        ctx.setProjectWorkspaceMessage("");
        return;
      }
      const artifactPageBtn = event.target.closest?.("[data-project-artifacts-page]");
      if (artifactPageBtn) {
        event.preventDefault();
        event.stopPropagation();
        if (artifactPageBtn.disabled) return;
        const projectId = String(artifactPageBtn.dataset.projectId || selectedProjectId() || "");
        const page = ctx.projectArtifactPagination?.(projectId) || { limit: 50, offset: 0 };
        const nextOffset = projectPageOffset(page, artifactPageBtn.dataset.projectArtifactsPage);
        const summary = ctx.projectSummary?.(projectId);
        ctx.setProjectArtifactPageOffset?.(projectId, nextOffset);
        await runProjectPager(artifactPageBtn, () => ctx.loadProjectArtifacts?.(projectId, summary, { offset: nextOffset, skipFinalRender: true }));
        return;
      }
      const targetPageBtn = event.target.closest?.("[data-project-targets-page]");
      if (targetPageBtn) {
        event.preventDefault();
        event.stopPropagation();
        if (targetPageBtn.disabled) return;
        const projectId = String(targetPageBtn.dataset.projectId || selectedProjectId() || "");
        const page = ctx.projectTargetPage?.(projectId) || { limit: 50, offset: 0 };
        const nextOffset = projectPageOffset(page, targetPageBtn.dataset.projectTargetsPage);
        await runProjectPager(targetPageBtn, () => ctx.loadProjectTargetPage?.(projectId, { offset: nextOffset, skipFinalRender: true }));
        return;
      }
      const targetFilterClear = event.target.closest?.("[data-project-target-filter-clear]");
      if (targetFilterClear) {
        event.preventDefault();
        event.stopPropagation();
        const projectId = String(targetFilterClear.dataset.projectId || selectedProjectId() || "");
        const targetId = String(targetFilterClear.dataset.projectTargetFilterClear || "");
        const filters = ctx.projectTargetFilterSet(projectId);
        if (targetId === "all") filters.clear();
        else if (targetId) filters.delete(targetId);
        ctx.renderProjectExplorer();
        return;
      }
      const runFilterClear = event.target.closest?.("[data-project-run-filter-clear]");
      if (runFilterClear) {
        event.preventDefault();
        event.stopPropagation();
        const projectId = String(runFilterClear.dataset.projectId || selectedProjectId() || "");
        const runId = String(runFilterClear.dataset.projectRunFilterClear || "");
        const filters = ctx.projectRunFilterSet(projectId);
        if (runId === "all") filters.clear();
        else if (runId) filters.delete(runId);
        ctx.renderProjectExplorer();
        return;
      }
      const statusFilterClear = event.target.closest?.("[data-project-finding-status-filter-clear]");
      if (statusFilterClear) {
        event.preventDefault();
        event.stopPropagation();
        const projectId = String(statusFilterClear.dataset.projectId || selectedProjectId() || "");
        const status = String(statusFilterClear.dataset.projectFindingStatusFilterClear || "");
        const filters = ctx.projectFindingStatusFilterSet(projectId);
        if (status === "all") filters.clear();
        else if (status) filters.delete(status);
        ctx.renderProjectExplorer();
        return;
      }
      const labelFilterClear = event.target.closest?.("[data-project-finding-label-filter-clear]");
      if (labelFilterClear) {
        event.preventDefault();
        event.stopPropagation();
        const projectId = String(labelFilterClear.dataset.projectId || selectedProjectId() || "");
        const labelValue = String(labelFilterClear.dataset.projectFindingLabelFilterClear || "");
        const filters = ctx.projectFindingLabelFilterSet(projectId);
        if (labelValue === "all") filters.clear();
        else if (labelValue) filters.delete(labelValue);
        ctx.renderProjectExplorer();
        return;
      }
      const commandFilterClear = event.target.closest?.("[data-project-finding-command-filter-clear]");
      if (commandFilterClear) {
        event.preventDefault();
        event.stopPropagation();
        const projectId = String(commandFilterClear.dataset.projectId || selectedProjectId() || "");
        const commandRoot = String(commandFilterClear.dataset.projectFindingCommandFilterClear || "");
        const filters = ctx.projectFindingCommandFilterSet(projectId);
        if (commandRoot === "all") filters.clear();
        else if (commandRoot) filters.delete(commandRoot);
        ctx.renderProjectExplorer();
        return;
      }
      const severityFilterClear = event.target.closest?.("[data-project-finding-severity-filter-clear]");
      if (severityFilterClear) {
        event.preventDefault();
        event.stopPropagation();
        const projectId = String(severityFilterClear.dataset.projectId || selectedProjectId() || "");
        const severity = String(severityFilterClear.dataset.projectFindingSeverityFilterClear || "");
        const filters = ctx.projectFindingSeverityFilterSet(projectId);
        if (severity === "all") filters.clear();
        else if (severity) filters.delete(severity);
        ctx.renderProjectExplorer();
        return;
      }
      const scopeFilterClear = event.target.closest?.("[data-project-finding-scope-filter-clear]");
      if (scopeFilterClear) {
        event.preventDefault();
        event.stopPropagation();
        const projectId = String(scopeFilterClear.dataset.projectId || selectedProjectId() || "");
        const scope = String(scopeFilterClear.dataset.projectFindingScopeFilterClear || "");
        const filters = ctx.projectFindingScopeFilterSet(projectId);
        if (scope === "all") filters.clear();
        else if (scope) filters.delete(scope);
        ctx.renderProjectExplorer();
        return;
      }
      const noteStateClear = event.target.closest?.("[data-project-finding-note-state-clear]");
      if (noteStateClear) {
        event.preventDefault();
        event.stopPropagation();
        const projectId = String(noteStateClear.dataset.projectId || selectedProjectId() || "");
        ctx.filtersController?.().setFindingNoteState(projectId, "all");
        ctx.renderProjectExplorer();
        return;
      }
      const orphanClear = event.target.closest?.("[data-project-finding-orphan-clear]");
      if (orphanClear) {
        event.preventDefault();
        event.stopPropagation();
        const projectId = String(orphanClear.dataset.projectId || selectedProjectId() || "");
        ctx.filtersController?.().setFindingOrphanFilter(projectId, "hide");
        ctx.renderProjectExplorer();
        return;
      }
      const allFilterClear = event.target.closest?.("[data-project-filter-clear-all]");
      if (allFilterClear) {
        event.preventDefault();
        event.stopPropagation();
        const projectId = String(allFilterClear.dataset.projectId || selectedProjectId() || "");
        ctx.filtersController?.().clearAllFilters(projectId);
        ctx.renderProjectExplorer();
        return;
      }
      const findingViewModeButton = event.target.closest?.("[data-project-finding-view-mode]");
      if (findingViewModeButton) {
        event.preventDefault();
        event.stopPropagation();
        const mode = String(findingViewModeButton.dataset.projectFindingViewMode || "list");
        ctx.setFindingViewMode(mode);
        ctx.renderProjectExplorer();
        return;
      }
      const tabBtn = event.target.closest?.("[data-project-tab]");
      if (tabBtn) {
        event.preventDefault();
        await ctx.flushProjectNotesAutosave();
        const nextTab = tabBtn.dataset.projectTab || "details";
        if (nextTab === workspaceTab()) {
          ctx.focusProjectWorkspaceTab?.(nextTab);
          return;
        }
        ctx.setWorkspaceTab(nextTab);
        if (nextTab !== "details") ctx.closeProjectTargetEditor();
        ctx.closeProjectEntityEditor();
        if (nextTab !== "entities") {
          ctx.entitiesController?.().setSelectMode(false);
          ctx.entitiesController?.().clearSelection();
        }
        if (nextTab !== "findings") {
          ctx.setFindingSelectMode(false);
          selectedFindingIds().clear();
        }
        ctx.setProjectWorkspaceMessage("");
        ctx.renderProjectExplorer();
        if (nextTab !== "details") {
          await ctx.ensureProjectSummary?.(selectedProjectId());
          ctx.renderProjectExplorer();
        }
        return;
      }
      const entityTabBtn = event.target.closest?.("[data-project-entity-tab]");
      if (entityTabBtn) {
        event.preventDefault();
        event.stopPropagation();
        const projectId = String(entityTabBtn.dataset.projectId || selectedProjectId() || "");
        ctx.entitiesController?.().setActiveTab(entityTabBtn.dataset.projectEntityTab || "ip");
        ctx.entitiesController?.().clearSelection();
        await Promise.resolve(ctx.entitiesController?.().ensureFilteredCounts(projectId));
        ctx.renderProjectExplorer();
        if (mobileView() === "detail") ctx.renderProjectMobileDetail();
        return;
      }
      const entityPageBtn = event.target.closest?.("[data-project-entities-page]");
      if (entityPageBtn) {
        event.preventDefault();
        event.stopPropagation();
        if (entityPageBtn.disabled) return;
        const projectId = String(entityPageBtn.dataset.projectId || selectedProjectId() || "");
        const page = ctx.entitiesController?.().page(projectId) || { limit: 50, offset: 0 };
        const nextOffset = projectPageOffset(page, entityPageBtn.dataset.projectEntitiesPage);
        ctx.entitiesController?.().setPageOffset(projectId, nextOffset);
        ctx.entitiesController?.().clearSelection();
        await runProjectPager(entityPageBtn, () => ctx.entitiesController?.().load(projectId, { offset: nextOffset, skipFinalRender: true }));
        return;
      }
      const entityCheckbox = event.target.closest?.("[data-project-entity-select]");
      if (entityCheckbox) {
        event.stopPropagation();
        const entityId = String(entityCheckbox.dataset.projectEntitySelect || "");
        ctx.entitiesController?.().toggleSelected(entityId, !!entityCheckbox.checked);
        ctx.renderProjectExplorer();
        return;
      }
      const findingCheckbox = event.target.closest?.("[data-project-finding-select]");
      if (findingCheckbox) {
        event.stopPropagation();
        const findingId = String(findingCheckbox.dataset.projectFindingSelect || "");
        if (findingId) {
          if (findingCheckbox.checked) selectedFindingIds().add(findingId);
          else selectedFindingIds().delete(findingId);
        }
        ctx.renderProjectExplorer();
        return;
      }
      const findingPagerButton = event.target.closest?.("[data-project-findings-page]");
      if (findingPagerButton) {
        event.preventDefault();
        if (findingPagerButton.disabled) return;
        const projectId = String(findingPagerButton.dataset.projectId || selectedProjectId() || "");
        const summary = ctx.projectSummary?.(projectId);
        const pagination = ctx.projectFindingPagination?.(projectId, summary) || {};
        const nextOffset = projectPageOffset(
          pagination,
          findingPagerButton.dataset.projectFindingsPage === "next" ? "next" : "prev"
        );
        ctx.setProjectFindingPageOffset?.(projectId, summary, nextOffset);
        await runProjectPager(findingPagerButton, () => ctx.projectFindingServerFiltersActive?.(projectId, summary) ? ctx.loadProjectFilteredFindings?.(projectId, summary, { offset: nextOffset, skipInitialRender: true }) : ctx.loadProjectFindings?.(projectId, { offset: nextOffset, skipInitialRender: true }));
        return;
      }
      const runPagerButton = event.target.closest?.("[data-project-runs-page]");
      if (runPagerButton) {
        event.preventDefault();
        if (runPagerButton.disabled) return;
        const projectId = String(runPagerButton.dataset.projectId || selectedProjectId() || "");
        const pagination = ctx.projectRunPagination?.(projectId) || {};
        const nextOffset = projectPageOffset(
          pagination,
          runPagerButton.dataset.projectRunsPage === "next" ? "next" : "prev"
        );
        ctx.setProjectRunPageOffset?.(projectId, nextOffset);
        await runProjectPager(runPagerButton, () => ctx.loadProjectRuns?.(projectId, { offset: nextOffset, skipFinalRender: true }));
        return;
      }
      const pagerButton = event.target.closest?.("[data-project-page]");
      if (pagerButton) {
        event.preventDefault();
        if (pagerButton.disabled) return;
        const pagination = ctx.projectPagination?.() || {};
        const nextOffset = projectPageOffset(
          pagination,
          pagerButton.dataset.projectPage === "next" ? "next" : "prev"
        );
        ctx.setProjectPaginationOffset?.(nextOffset);
        await ctx.refreshProjectWorkspace();
        return;
      }
      const btn = event.target.closest?.("[data-project-action]");
      if (!btn) return;
      if (btn.getAttribute("role") === "button" && event.target.closest?.("select, input, textarea, a, button")) return;
      event.preventDefault();
      await handleActionButton(btn);
    }
    async function handleActionButton(btn) {
      const action = btn.dataset.projectAction || "";
      const projectId = btn.dataset.projectId || "";
      let successMessage = "";
      try {
        if (action === "select") {
          await ctx.flushProjectNotesAutosave();
          ctx.setSelectedProjectId(projectId);
          ctx.closeProjectTargetEditor();
          ctx.setProjectWorkspaceMessage("");
          ctx.renderProjectWorkspace();
          if (ctx.workspaceTab?.() !== "details") {
            await ctx.ensureProjectSummary?.(projectId);
            ctx.renderProjectWorkspace();
          }
          return;
        } else if (action === "use") {
          await ctx.projectWorkspaceRequest("/projects/active", {
            method: "POST",
            body: JSON.stringify({ project_id: projectId })
          });
          successMessage = "Active project updated.";
        } else if (action === "clear") {
          await ctx.projectWorkspaceRequest("/projects/active", { method: "DELETE" });
          successMessage = "Active project cleared.";
        } else if (action === "archive") {
          await ctx.projectWorkspaceRequest(`/projects/${encodeURIComponent(projectId)}`, {
            method: "PUT",
            body: JSON.stringify({ status: "archived" })
          });
          const activeProject = ctx.activeProject?.();
          if (activeProject && String(activeProject.id || "") === projectId) {
            await ctx.projectWorkspaceRequest("/projects/active", { method: "DELETE" });
          }
          successMessage = "Project archived.";
        } else if (action === "unarchive") {
          await ctx.projectWorkspaceRequest(`/projects/${encodeURIComponent(projectId)}`, {
            method: "PUT",
            body: JSON.stringify({ status: "active" })
          });
          successMessage = "Project unarchived.";
        } else if (action === "delete") {
          const project = projectRows().find((item) => String(item.id || "") === projectId) || null;
          const confirmed = await ctx.confirmProjectDelete(project ? ctx.projectDisplayName(project) : projectId);
          if (!confirmed) return;
          await ctx.projectWorkspaceRequest(`/projects/${encodeURIComponent(projectId)}`, { method: "DELETE" });
          if (selectedProjectId() === projectId) {
            ctx.setSelectedProjectId("");
            ctx.closeProjectTargetEditor();
          }
          await ctx.refreshProjectWorkspace();
          ctx.setProjectWorkspaceMessage("Project deleted.");
          return;
        } else if (action === "edit-project-metadata") {
          const project = projectFromRowsOrSummary(projectId);
          if (!project) throw new Error("Project is missing its details.");
          ctx.setProjectWorkspaceMessage("");
          ctx.openProjectEntityEditor(projectId, "project", project);
          return;
        } else if (action === "open-atlas") {
          const project = projectFromRowsOrSummary(projectId);
          ctx.closeProjectWorkspace({ refocus: false });
          const openAtlas = typeof exportedOpenAtlas !== "undefined" && exportedOpenAtlas || null;
          if (typeof openAtlas === "function") {
            void openAtlas({
              source: "project-workspace",
              projectId,
              projectName: project ? ctx.projectDisplayName(project) : ""
            });
          }
          return;
        } else if (action === "open-findings-board") {
          const project = projectFromRowsOrSummary(projectId);
          const openFindingsBoard = typeof ctx.openFindingsBoard === "function" ? ctx.openFindingsBoard : exportedOpenFindingsBoard;
          if (typeof openFindingsBoard === "function") {
            ctx.closeProjectWorkspace({ refocus: false });
            void openFindingsBoard({
              source: "project-workspace",
              projectId,
              projectName: project ? ctx.projectDisplayName(project) : ""
            });
          }
          return;
        } else if (action === "open-project-entity") {
          const summary = ctx.projectSummary?.(projectId);
          const entityId = String(btn.dataset.entityId || "");
          const entity = ctx.entitiesController?.().byId(summary, entityId) || {
            id: entityId,
            type: String(btn.dataset.entityType || ""),
            canonical_value: String(btn.dataset.entityValue || "")
          };
          ctx.openProjectEntityInAtlas(projectId, summary, entity);
          return;
        } else if (action === "toggle-project-entity-row") {
          const entityId = String(btn.dataset.entityId || "");
          ctx.entitiesController?.().toggleSelected(entityId);
          ctx.renderProjectExplorer();
          return;
        } else if (action === "toggle-project-entity-select") {
          const nextMode = !ctx.entitySelectMode();
          if (nextMode && !activeTeamScopeCan2("mutate_projects")) {
            denyTeamScopeAction("change team projects");
            return;
          }
          ctx.entitiesController?.().setSelectMode(nextMode);
          if (!nextMode) ctx.entitiesController?.().clearSelection();
          ctx.renderProjectExplorer();
          return;
        } else if (action === "select-all-project-entities") {
          if (!activeTeamScopeCan2("mutate_projects")) {
            denyTeamScopeAction("change team projects");
            return;
          }
          ctx.entitiesController?.().selectAllForActiveTab(ctx.projectSummary?.(projectId));
          ctx.renderProjectExplorer();
          return;
        } else if (action === "clear-project-entities") {
          ctx.entitiesController?.().clearSelection();
          ctx.renderProjectExplorer();
          return;
        } else if (action === "bulk-unlink-project-entities") {
          if (!selectedEntityIds().size) return;
          const count = selectedEntityIds().size;
          const confirmed = await ctx.confirmProjectDestructive({
            body: `Unlink ${count} ${count === 1 ? "entity" : "entities"} from this project?`,
            note: "The entities stay in Atlas.",
            actionLabel: "Unlink",
            actionId: "unlink"
          });
          if (!confirmed) return;
          await ctx.projectWorkspaceRequest(`/projects/${encodeURIComponent(projectId)}/links`, {
            method: "DELETE",
            body: JSON.stringify({ entity_type: "atlas_entity", entity_ids: [...selectedEntityIds()] })
          });
          selectedEntityIds().clear();
          ctx.entitiesController?.().setSelectMode(false);
          await ctx.refreshProjectWorkspace();
          ctx.setProjectWorkspaceMessage("Entities unlinked from project.");
          return;
        } else if (action === "unlink-project-entity") {
          const entityId = String(btn.dataset.entityId || "");
          if (!projectId || !entityId) throw new Error("Entity link is missing its identifier.");
          const confirmed = await ctx.confirmProjectDestructive({
            body: "Unlink this entity from the project?",
            note: "The entity stays in Atlas.",
            actionLabel: "Unlink",
            actionId: "unlink"
          });
          if (!confirmed) return;
          await ctx.projectWorkspaceRequest(`/projects/${encodeURIComponent(projectId)}/links`, {
            method: "DELETE",
            body: JSON.stringify({ entity_type: "atlas_entity", entity_id: entityId })
          });
          await ctx.refreshProjectWorkspace();
          ctx.setProjectWorkspaceMessage("Entity unlinked from project.");
          return;
        } else if (action === "export-project-entities-csv" || action === "export-project-entities-jsonl") {
          const format = action === "export-project-entities-jsonl" ? "jsonl" : "csv";
          await ctx.entitiesController?.().exportEntities(projectId, format);
          return;
        } else if (action === "open-entity-picker") {
          ctx.openProjectEntityPicker(projectId);
          return;
        } else if (action === "toggle-project-finding-select") {
          const nextMode = !ctx.findingSelectMode();
          if (nextMode && !activeTeamScopeCan2("triage_findings")) {
            denyTeamScopeAction("triage team findings");
            return;
          }
          ctx.setFindingSelectMode(nextMode);
          if (!nextMode) selectedFindingIds().clear();
          ctx.renderProjectExplorer();
          return;
        } else if (action === "toggle-project-finding-row") {
          const findingId = String(btn.dataset.findingId || "");
          if (findingId) {
            if (selectedFindingIds().has(findingId)) selectedFindingIds().delete(findingId);
            else selectedFindingIds().add(findingId);
          }
          ctx.renderProjectExplorer();
          return;
        } else if (action === "select-all-project-findings") {
          if (!activeTeamScopeCan2("triage_findings")) {
            denyTeamScopeAction("triage team findings");
            return;
          }
          ctx.filteredProjectFindings(projectId, ctx.projectSummary?.(projectId)).forEach((finding) => {
            if (finding && finding.id) selectedFindingIds().add(String(finding.id));
          });
          ctx.renderProjectExplorer();
          return;
        } else if (action === "clear-project-findings") {
          selectedFindingIds().clear();
          ctx.renderProjectExplorer();
          return;
        } else if (action === "bulk-delete-project-findings") {
          if (!selectedFindingIds().size) return;
          const count = selectedFindingIds().size;
          const confirmed = await ctx.confirmProjectDestructive({
            body: `Delete ${count} Atlas ${count === 1 ? "finding" : "findings"}?`,
            note: "This removes the selected findings from Atlas, not just this project.",
            actionLabel: "Delete",
            actionId: "delete"
          });
          if (!confirmed) return;
          await ctx.projectWorkspaceRequest("/atlas/findings/bulk-delete", {
            method: "POST",
            body: JSON.stringify({ finding_ids: [...selectedFindingIds()] })
          });
          selectedFindingIds().clear();
          ctx.setFindingSelectMode(false);
          ctx.invalidateProjectFindings(projectId);
          await ctx.loadProjectFindings(projectId);
          await ctx.refreshProjectWorkspace();
          ctx.setProjectWorkspaceMessage("Findings deleted.");
          return;
        } else if (action === "new-target") {
          ctx.setProjectWorkspaceMessage("");
          ctx.openProjectTargetEditor(projectId);
          return;
        }
        const packagesController = ctx.packagesController?.();
        if (packagesController && await packagesController.handleAction(btn)) return;
        if (action === "edit-target") {
          const targetId = String(btn.dataset.targetId || "");
          const target = ctx.projectTargetById?.(projectId, targetId) || ctx.projectTargetItems(ctx.projectSummary?.(projectId)).find((item) => String(item.id || "") === targetId);
          if (!target) throw new Error("Target is missing its details.");
          ctx.setProjectWorkspaceMessage("");
          ctx.openProjectTargetEditor(projectId, target);
          return;
        } else if (action === "edit-finding-metadata") {
          const findingId = String(btn.dataset.findingId || "");
          const finding = projectFindingById(projectId, findingId);
          if (!finding) throw new Error("Finding is missing its details.");
          ctx.setProjectWorkspaceMessage("");
          ctx.openProjectEntityEditor(projectId, "finding", finding);
          return;
        } else if (action === "edit-finding-triage") {
          const findingId = String(btn.dataset.findingId || "");
          const finding = projectFindingById(projectId, findingId);
          if (!finding) throw new Error("Finding is missing its details.");
          ctx.setProjectWorkspaceMessage("");
          const findingTriageEditor = ctx.findingTriageEditor || DarklabFindingTriageEditor;
          if (!findingTriageEditor || typeof findingTriageEditor.open !== "function") {
            throw new Error("Finding triage editor is not available.");
          }
          await findingTriageEditor.open(finding, {
            canEdit: activeTeamScopeCan2("triage_findings"),
            onSaved: async (triage) => {
              const compact = findingTriageEditor.compactTriage(triage);
              ctx.updateCachedProjectFinding?.(projectId, findingId, {
                triage: compact,
                verification_status: compact.verification_status
              });
              ctx.renderProjectExplorer?.();
              if (mobileView() === "detail" && workspaceTab() === "findings" && selectedProjectId() === projectId) {
                ctx.renderProjectMobileDetail?.();
              }
              ctx.setProjectWorkspaceMessage("Finding triage saved.");
            }
          });
          return;
        } else if (action === "edit-run-metadata") {
          const runId = String(btn.dataset.runId || "");
          const run = ctx.projectRunItems(ctx.projectSummary?.(projectId)).find((item) => String(item.id || "") === runId);
          if (!run) throw new Error("Run is missing its details.");
          ctx.setProjectWorkspaceMessage("");
          ctx.openProjectEntityEditor(projectId, "run", run);
          return;
        } else if (action === "edit-artifact-metadata") {
          const artifactId = String(btn.dataset.artifactId || "");
          const artifact = ctx.projectArtifactItems(ctx.projectSummary?.(projectId)).find((item) => String(item.id || "") === artifactId);
          if (!artifact) throw new Error("Artifact is missing its details.");
          ctx.setProjectWorkspaceMessage("");
          ctx.openProjectEntityEditor(projectId, "run_file_artifact", artifact);
          return;
        } else if (action === "delete-target") {
          const targetId = String(btn.dataset.targetId || "");
          if (!projectId || !targetId) throw new Error("Target is missing its identifier.");
          const confirmed = await ctx.confirmProjectTargetDelete(btn.dataset.targetValue || "");
          if (!confirmed) return;
          await ctx.projectWorkspaceRequest(`/projects/${encodeURIComponent(projectId)}/targets/${encodeURIComponent(targetId)}`, {
            method: "DELETE"
          });
          ctx.clearEditingTargetIf(targetId);
          ctx.removeCachedProjectTarget?.(projectId, targetId);
          await ctx.loadProjectTargetPage?.(projectId, { skipFinalRender: true });
          ctx.renderProjectExplorer?.();
          if (mobileView() === "detail") ctx.renderProjectMobileDetail?.();
          ctx.loadProjectAutocompleteTargets?.();
          ctx.setProjectWorkspaceMessage("Target removed.");
          return;
        } else if (action === "confirm-target" || action === "dismiss-target") {
          const targetId = String(btn.dataset.targetId || "");
          if (!projectId || !targetId) throw new Error("Target is missing its identifier.");
          const reviewState = action === "confirm-target" ? "confirmed" : "dismissed";
          const resp = await ctx.projectWorkspaceRequest(`/projects/${encodeURIComponent(projectId)}/targets/${encodeURIComponent(targetId)}`, {
            method: "PUT",
            body: JSON.stringify({ review_state: reviewState })
          });
          const data = await resp.json().catch(() => ({}));
          if (reviewState === "dismissed") {
            ctx.removeCachedProjectTarget?.(projectId, targetId);
          } else {
            const target = data && data.target && typeof data.target === "object" ? data.target : { review_state: reviewState, status: reviewState };
            ctx.updateCachedProjectTarget?.(projectId, targetId, target);
          }
          ctx.renderProjectExplorer?.();
          ctx.loadProjectAutocompleteTargets?.();
          ctx.setProjectWorkspaceMessage(reviewState === "confirmed" ? "Target confirmed." : "Target dismissed.");
          return;
        } else if (action === "filter-run" || action === "filter-run-findings" || action === "filter-run-artifacts") {
          const runId = String(btn.dataset.runId || "").trim();
          if (!projectId || !runId) throw new Error("Run is missing its identifier.");
          const filters = ctx.projectRunFilterSet(projectId);
          filters.clear();
          filters.add(runId);
          if (action === "filter-run-findings") ctx.setWorkspaceTab("findings");
          if (action === "filter-run-artifacts") ctx.setWorkspaceTab("artifacts");
          ctx.renderProjectExplorer();
          return;
        } else if (action === "mobile-compare-runs") {
          ctx.openProjectMobileCompareSheet(projectId, btn);
          return;
        } else if (action === "compare-runs") {
          const controls = ctx.projectExplorerBody?.querySelector(".project-run-compare-controls");
          const mode = String(ctx.projectExplorerBody?.querySelector("[data-project-compare-mode]")?.value || "run");
          const targetValue = String(ctx.projectExplorerBody?.querySelector("[data-project-compare-target]")?.value || "").trim();
          const leftId = String(ctx.projectExplorerBody?.querySelector('[data-project-compare-run="left"]')?.value || "");
          ctx.compareProjectRuns(projectId, leftId, mode, targetValue, controls);
          return;
        } else if (action === "link-last-run") {
          await ctx.linkLastRunToProject(projectId, ctx.projectSummary?.(projectId));
          return;
        } else if (action === "open-run") {
          const runId = String(btn.dataset.runId || "").trim();
          if (!runId) throw new Error("Run is missing its identifier.");
          const restore = restoreHistoryRun();
          if (!restore) throw new Error("History restore is not available.");
          await restore({
            id: runId,
            command: String(btn.dataset.runCommand || ""),
            full_output_available: true
          }, {
            hidePanelOnSuccess: false
          });
          ctx.closeProjectWorkspace({ refocus: false });
          return;
        } else if (action === "unlink-run") {
          const runId = String(btn.dataset.runId || "").trim();
          if (!projectId || !runId) throw new Error("Run link is missing its identifier.");
          const confirmed = await ctx.confirmProjectRunUnlink(btn.dataset.runCommand || "");
          if (!confirmed) return;
          await ctx.projectWorkspaceRequest(`/projects/${encodeURIComponent(projectId)}/links`, {
            method: "DELETE",
            body: JSON.stringify({ entity_type: "run", entity_id: runId })
          });
          await ctx.refreshProjectWorkspace();
          ctx.setProjectWorkspaceMessage("Run removed from project.");
          return;
        } else if (action === "open-finding") {
          const runId = String(btn.dataset.runId || "").trim();
          if (!runId) throw new Error("Finding is missing its source run.");
          const lineIndexRaw = String(btn.dataset.lineIndex || "").trim();
          const lineIndex = lineIndexRaw === "" ? null : Number(lineIndexRaw);
          const restore = restoreHistoryRun();
          if (!restore) throw new Error("History restore is not available.");
          await restore({
            id: runId,
            command: String(btn.dataset.runCommand || ""),
            full_output_available: true
          }, {
            hidePanelOnSuccess: false,
            highlightLineIndex: Number.isInteger(lineIndex) ? lineIndex : null
          });
          ctx.closeProjectWorkspace({ refocus: false });
          return;
        } else if (action === "artifact-preview") {
          const artifactId = String(btn.dataset.artifactId || "").trim();
          if (!projectId || !artifactId) throw new Error("Artifact is missing its identifier.");
          await ctx.previewProjectArtifact(projectId, artifactId);
          return;
        } else if (action === "artifact-download") {
          const artifactId = String(btn.dataset.artifactId || "").trim();
          if (!projectId || !artifactId) throw new Error("Artifact is missing its identifier.");
          await ctx.downloadProjectArtifact(projectId, artifactId, btn.dataset.artifactPath || "");
          return;
        } else if (action === "package-edit" || action === "package-download" || action === "package-repackage" || action === "package-manifest" || action === "package-delete") {
          const packageId = String(btn.dataset.packageId || "").trim();
          if (!projectId || !packageId) throw new Error("Package is missing its identifier.");
          const pkg = ctx.projectPackageById(ctx.projectSummary?.(projectId), packageId) || { id: packageId, name: packageId };
          if (action === "package-edit") {
            ctx.openProjectEntityEditor(projectId, "package", pkg);
            return;
          }
          if (action === "package-download") {
            ctx.setProjectPackageDownloadBusy(btn, true);
            try {
              await ctx.downloadProjectPackage(projectId, pkg);
            } finally {
              ctx.setProjectPackageDownloadBusy(btn, false);
            }
            return;
          }
          if (action === "package-repackage" || action === "package-manifest") {
            const resp = await ctx.projectWorkspaceRequest(
              `/projects/${encodeURIComponent(projectId)}/packages/${encodeURIComponent(packageId)}`,
              { cache: "no-store" }
            );
            const data = await resp.json().catch(() => ({}));
            if (action === "package-repackage") {
              ctx.openProjectPackageWizardFromPackage(projectId, data.package || pkg);
              return;
            }
            ctx.openProjectPackageManifest(data.package || pkg);
            return;
          }
          const confirmed = await ctx.confirmProjectPackageDelete(pkg.name || packageId);
          if (!confirmed) return;
          await ctx.projectWorkspaceRequest(`/projects/${encodeURIComponent(projectId)}/packages/${encodeURIComponent(packageId)}`, {
            method: "DELETE"
          });
          ctx.closeProjectPackageManifest();
          await ctx.refreshProjectWorkspace();
          ctx.setProjectWorkspaceMessage("Package deleted.");
          return;
        }
        await ctx.refreshProjectWorkspace();
        if (successMessage) ctx.setProjectWorkspaceMessage(successMessage);
      } catch (err) {
        ctx.setProjectWorkspaceMessage(err.message || "Project action failed.", { error: true });
      }
    }
    function bindEvents() {
      ctx.projectWorkspaceModal?.addEventListener("input", (event) => {
        void handleInput(event);
      });
      ctx.projectWorkspaceModal?.addEventListener("change", (event) => {
        void handleChange(event);
      });
      document.addEventListener("input", handleDocumentPickerInput);
      document.addEventListener("change", handleDocumentPickerChange);
      document.addEventListener("click", (event) => {
        void handleDocumentPickerClick(event);
      });
      document.addEventListener("click", handleDocumentFilterMenuClick, true);
      ctx.projectWorkspaceModal?.addEventListener("pointerdown", handlePointerDown);
      ctx.projectWorkspaceModal?.addEventListener("mousedown", handlePointerDown);
      ctx.projectWorkspaceModal?.addEventListener("click", (event) => {
        void handleClick(event);
      });
    }
    return {
      bindEvents,
      handleActionButton,
      handleChange,
      handleClick,
      handleInput,
      handlePointerDown
    };
  }
  const DarklabProjectWorkspaceEvents = {
    createProjectWorkspaceEventsController
  };
  exportedDarklabProjectWorkspaceEvents = DarklabProjectWorkspaceEvents;
})(globalThis);
export {
  exportedDarklabProjectWorkspaceEvents as DarklabProjectWorkspaceEvents
};
