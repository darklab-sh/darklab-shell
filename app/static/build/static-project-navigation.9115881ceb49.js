import {
  bindTabStripEdgeListener,
  syncActiveTabStripScroll,
  syncTabStripEdges
} from "./static-chunk-ebgxhzia.8240f1614c32.js";
import {
  exportedOpenAtlas
} from "./static-chunk-k5eqxewa.a48fecea544c.js";
import "./static-chunk-h7v2dm32.87e4312006bc.js";
import "./static-chunk-wkdqs5l5.75c18d0d56e7.js";
import "./static-chunk-skfe6pvf.334da5004f60.js";
import "./static-chunk-maah23qz.ef218783e6a2.js";
import "./static-chunk-3jl77jd6.5db9023622ce.js";
import "./static-chunk-dil5yyjg.6d28df9092db.js";
import "./static-chunk-azqlfkpx.da3a241d7053.js";
import "./static-chunk-vzfenxxg.b8dadbb5046d.js";
import "./static-chunk-3jpzlov4.47e7ebc68e55.js";
import "./static-chunk-iimv3vvo.e054c6ada14d.js";
import "./static-chunk-ylgcpl7n.752d37b456dc.js";
import "./static-chunk-woazwvu4.87340bdecc1f.js";
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

// app/static/js/features/projects/project_navigation.js
var exportedDarklabProjectNavigation = null;
(function projectNavigationModule(global) {
  "use strict";
  function createProjectNavigationController(context) {
    const ctx = context || {};
    const mobileTabEdgeOptions = { wrapSelector: ".project-mobile-tabs-wrap" };
    const desktopTabEdgeOptions = {
      wrapSelector: ".project-explorer-tabs-wrap",
      scrollOnlyIfNeeded: true
    };
    let desktopTabsResizeObserver = null;
    function formatCompactCount(value) {
      const count = Number(value || 0);
      if (!Number.isFinite(count) || count <= 0) return "0";
      if (count >= 1e6) return `${(count / 1e6).toFixed(count >= 1e7 ? 0 : 1)}m`;
      if (count >= 1e3) return `${(count / 1e3).toFixed(count >= 1e4 ? 0 : 1)}k`;
      return String(count);
    }
    function projectFindingSummary(summary) {
      return summary && summary.finding_summary && typeof summary.finding_summary === "object" ? summary.finding_summary : null;
    }
    function findingStateCount(summary, group, keys) {
      const source = projectFindingSummary(summary)?.[group];
      if (!source || typeof source !== "object") return 0;
      return keys.reduce((total, key) => total + Number(source[key] || 0), 0);
    }
    function findingTabSummaryText(summary, totalCount) {
      const findingSummary = projectFindingSummary(summary);
      if (!findingSummary) return String(totalCount);
      const unreviewed = findingStateCount(summary, "review_states", ["new"]);
      const highSignal = findingStateCount(summary, "severities", ["critical", "high"]);
      const parts = [String(totalCount)];
      if (unreviewed > 0) parts.push(`${formatCompactCount(unreviewed)} new`);
      if (highSignal > 0) parts.push(`${formatCompactCount(highSignal)} high`);
      return parts.join(" · ");
    }
    function tabCountText(projectId, summary, tabId, total) {
      const totalCount = Number(total || 0);
      const targetFiltersActive = ctx.projectTargetFilterActive(projectId, summary);
      const runFiltersActive = ctx.projectRunFilterActive(projectId, summary);
      if (tabId === "findings") {
        if (!ctx.projectFindingServerFiltersActive(projectId, summary)) {
          return findingTabSummaryText(summary, totalCount);
        }
        const page = ctx.projectFindingPagination?.(projectId, summary) || {};
        const filteredTotal = Number(page.total || ctx.filteredProjectFindings(projectId, summary).length);
        if (!page.loaded && !filteredTotal) return String(totalCount);
        return `${filteredTotal}/${totalCount}`;
      }
      if (tabId === "runs") {
        if (!targetFiltersActive && !runFiltersActive) return String(totalCount);
        if (targetFiltersActive && !ctx.projectFindingsLoaded(projectId)) return String(totalCount);
        return `${ctx.filteredProjectRuns(projectId, summary).length}/${totalCount}`;
      }
      if (tabId === "entities") {
        if (typeof ctx.projectEntityTabCountText === "function") {
          return ctx.projectEntityTabCountText(projectId, summary, totalCount);
        }
        return String(totalCount);
      }
      if (tabId === "artifacts") {
        if (!targetFiltersActive && !runFiltersActive) return String(totalCount);
        if (targetFiltersActive && !ctx.projectFindingsLoaded(projectId)) return String(totalCount);
        return `${ctx.filteredProjectArtifacts(projectId, summary).length}/${totalCount}`;
      }
      return String(totalCount);
    }
    function mobileTabItems(projectId, summary) {
      const counts = ctx.projectCounts(summary);
      const clamp = (value) => {
        const count = Number(value || 0);
        if (!Number.isFinite(count) || count <= 0) return "0";
        return count > 999 ? "999+" : String(count);
      };
      return [
        { id: "details", label: "Details" },
        { id: "runs", label: "Runs", count: clamp(counts.runs) },
        { id: "entities", label: "Entities", count: tabCountText(projectId, summary, "entities", counts.entities) },
        { id: "findings", label: "Findings", count: clamp(counts.findings) },
        ctx.projectArtifactsVisible() ? { id: "artifacts", label: "Artifacts", count: clamp(counts.artifacts) } : null,
        { id: "packages", label: "Packages", count: clamp(counts.packages) },
        { id: "report", label: "Report" },
        { id: "monitoring", label: "Monitoring" },
        { id: "activity", label: "Activity" }
      ].filter(Boolean);
    }
    function renderProjectHeader(project, summary, options = {}) {
      const header = document.createElement("div");
      header.className = "project-explorer-header";
      const titleWrap = document.createElement("div");
      titleWrap.className = "project-explorer-title-wrap";
      const title = document.createElement("div");
      title.className = "project-explorer-title";
      title.textContent = ctx.projectDisplayName(project);
      const meta = document.createElement("div");
      meta.className = "project-explorer-meta";
      meta.textContent = [
        String(project.slug || project.id || ""),
        String(project.id || "")
      ].filter(Boolean).join(ctx.metaSeparator || " - ");
      titleWrap.append(title, meta);
      ctx.appendProjectLabelChips(titleWrap, project);
      const activeProject = ctx.activeProject();
      const activeId = activeProject && activeProject.id ? String(activeProject.id) : "";
      const actions = document.createElement("div");
      actions.className = "project-explorer-actions";
      if (String(project.id || "") === activeId) {
        const pill = document.createElement("span");
        pill.className = "project-explorer-active-pill";
        pill.textContent = "active";
        actions.appendChild(pill);
        actions.appendChild(ctx.makeProjectButton("Clear active", "clear", String(project.id || "")));
      } else if (project.status !== "archived") {
        actions.appendChild(ctx.makeProjectButton("Use as active", "use", String(project.id || "")));
      }
      if (project.status !== "archived") {
        actions.appendChild(ctx.makeProjectButton("Archive", "archive", String(project.id || "")));
      } else {
        actions.appendChild(ctx.makeProjectButton("Unarchive", "unarchive", String(project.id || "")));
      }
      const openAtlas = typeof exportedOpenAtlas === "function" ? exportedOpenAtlas : null;
      if (typeof openAtlas === "function") {
        actions.appendChild(ctx.makeProjectButton("Open in Atlas", "open-atlas", String(project.id || "")));
      }
      actions.appendChild(ctx.makeProjectButton("Delete", "delete", String(project.id || ""), "destructive"));
      header.append(titleWrap, actions);
      const tabs = document.createElement("div");
      tabs.className = "project-explorer-tabs tab-strip";
      tabs.setAttribute("role", "tablist");
      tabs.setAttribute("aria-label", "Project sections");
      const tabsWrap = document.createElement("div");
      tabsWrap.className = "tab-strip-wrap project-explorer-tabs-wrap";
      const scrollLeft = createDesktopTabScrollButton("left");
      const scrollRight = createDesktopTabScrollButton("right");
      const tabCounts = ctx.projectCounts(summary);
      const projectId = String(project.id || "");
      const tabItems = [
        { id: "details", label: "Details" },
        { id: "runs", label: "Runs", count: tabCountText(projectId, summary, "runs", tabCounts.runs) },
        { id: "entities", label: "Entities", count: tabCountText(projectId, summary, "entities", tabCounts.entities) },
        { id: "findings", label: "Findings", count: tabCountText(projectId, summary, "findings", tabCounts.findings) },
        ctx.projectArtifactsVisible() ? { id: "artifacts", label: "Artifacts", count: tabCountText(projectId, summary, "artifacts", tabCounts.artifacts) } : null,
        { id: "packages", label: "Packages", count: tabCounts.packages },
        { id: "report", label: "Report" },
        { id: "monitoring", label: "Monitoring" },
        { id: "activity", label: "Activity" }
      ].filter(Boolean);
      tabItems.forEach(({ id, label, count }) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "tab-strip-item project-explorer-tab" + (ctx.projectWorkspaceTab() === id ? " is-active" : "");
        btn.dataset.projectTab = id;
        btn.setAttribute("role", "tab");
        btn.setAttribute("aria-selected", ctx.projectWorkspaceTab() === id ? "true" : "false");
        btn.setAttribute("aria-pressed", ctx.projectWorkspaceTab() === id ? "true" : "false");
        btn.textContent = count === void 0 ? label : `${label} (${count})`;
        ctx.bindProjectRuntimePressable(btn);
        tabs.appendChild(btn);
      });
      tabsWrap.append(scrollLeft, tabs, scrollRight);
      const initialTabsScrollLeft = Math.max(0, Number(options.initialTabsScrollLeft || 0));
      if (initialTabsScrollLeft > 0) tabs.scrollLeft = initialTabsScrollLeft;
      bindDesktopTabControls(tabs);
      syncDesktopActiveTabScroll(tabs);
      return [header, tabsWrap];
    }
    function createDesktopTabScrollButton(direction) {
      const isLeft = direction === "left";
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "tabs-scroll-btn btn btn-ghost btn-icon-only btn-compact project-explorer-tabs-scroll-btn u-hidden";
      btn.dataset.projectTabsScroll = direction;
      btn.setAttribute("aria-label", isLeft ? "Scroll project tabs left" : "Scroll project tabs right");
      btn.setAttribute("aria-hidden", "true");
      btn.title = isLeft ? "Scroll project tabs left" : "Scroll project tabs right";
      btn.disabled = true;
      ctx.bindProjectRuntimePressable(btn);
      return btn;
    }
    function renderMobileDetailTopbar(project, activeId) {
      if (!ctx.projectMobileDetailTopbar) return;
      ctx.projectMobileDetailTopbar.replaceChildren();
      const back = document.createElement("button");
      back.type = "button";
      back.className = "btn btn-ghost btn-compact project-mobile-back-btn";
      back.dataset.projectMobileAction = "back-to-list";
      back.setAttribute("aria-label", "Back to project list");
      back.textContent = ctx.mobileBackText || "< Back";
      ctx.bindProjectRuntimePressable(back);
      const titleWrap = document.createElement("div");
      titleWrap.className = "project-mobile-detail-title-wrap";
      const title = document.createElement("div");
      title.className = "project-mobile-detail-title";
      title.textContent = project ? ctx.projectDisplayName(project) : "Project";
      titleWrap.appendChild(title);
      const statusText = project && String(project.id || "") === activeId ? "active" : project && ctx.projectIsArchived(project) ? "archived" : "";
      const statusSlot = document.createElement("div");
      statusSlot.className = "project-mobile-detail-status-slot";
      if (statusText) {
        const status = document.createElement("span");
        status.className = "project-workspace-status" + (statusText === "active" ? " is-active" : "");
        status.textContent = statusText;
        statusSlot.appendChild(status);
      }
      ctx.projectMobileDetailTopbar.append(back, titleWrap, statusSlot);
    }
    function renderMobileTabs(projectId, summary) {
      if (!ctx.projectMobileTabs) return;
      ctx.projectMobileTabs.replaceChildren();
      const items = mobileTabItems(projectId, summary);
      if (!items.some((item) => item.id === ctx.projectWorkspaceTab())) ctx.setProjectWorkspaceTab("details");
      items.forEach((item) => {
        const tab = document.createElement("button");
        tab.type = "button";
        tab.className = "tab-strip-item project-mobile-tab" + (ctx.projectWorkspaceTab() === item.id ? " is-active" : "");
        tab.dataset.projectMobileDetailTab = item.id;
        tab.setAttribute("role", "tab");
        tab.setAttribute("aria-selected", ctx.projectWorkspaceTab() === item.id ? "true" : "false");
        tab.setAttribute("aria-pressed", ctx.projectWorkspaceTab() === item.id ? "true" : "false");
        const label = document.createElement("span");
        label.className = "project-mobile-tab-label";
        label.textContent = item.label;
        tab.appendChild(label);
        if (item.count !== void 0) {
          const count = document.createElement("span");
          count.className = "project-mobile-tab-count";
          count.textContent = item.count;
          tab.appendChild(count);
        }
        ctx.bindProjectRuntimePressable(tab);
        ctx.projectMobileTabs.appendChild(tab);
      });
      syncMobileActiveTabScroll();
    }
    function syncMobileActiveTabScroll() {
      if (typeof syncActiveTabStripScroll === "function") {
        syncActiveTabStripScroll(ctx.projectMobileTabs, mobileTabEdgeOptions);
      }
    }
    function syncDesktopActiveTabScroll(strip) {
      if (typeof syncActiveTabStripScroll === "function") {
        syncActiveTabStripScroll(strip, desktopTabEdgeOptions);
      }
      scheduleDesktopTabScrollSync(strip);
    }
    function bindDesktopTabControls(strip) {
      if (typeof bindTabStripEdgeListener === "function") {
        bindTabStripEdgeListener(strip, desktopTabEdgeOptions);
      }
      if (!strip || typeof strip.closest !== "function") return;
      const wrap = strip.closest(".project-explorer-tabs-wrap");
      if (!wrap) return;
      wrap.querySelector('[data-project-tabs-scroll="left"]')?.addEventListener("click", () => scrollDesktopTabs(strip, -1));
      wrap.querySelector('[data-project-tabs-scroll="right"]')?.addEventListener("click", () => scrollDesktopTabs(strip, 1));
      strip.addEventListener("scroll", () => syncDesktopTabScrollControls(strip), { passive: true });
      if (desktopTabsResizeObserver) desktopTabsResizeObserver.disconnect();
      if (typeof ResizeObserver === "function") {
        desktopTabsResizeObserver = new ResizeObserver(() => syncDesktopTabScrollControls(strip));
        desktopTabsResizeObserver.observe(wrap);
        desktopTabsResizeObserver.observe(strip);
      }
      scheduleDesktopTabScrollSync(strip);
    }
    function scheduleDesktopTabScrollSync(strip) {
      if (!strip) return;
      window.setTimeout(() => syncDesktopTabScrollControls(strip), 0);
    }
    function scrollDesktopTabs(strip, direction) {
      if (!strip) return;
      const distance = Math.max(180, Math.floor(Number(strip.clientWidth || 0) * 0.7) || 220);
      if (typeof strip.scrollBy === "function") {
        strip.scrollBy({ left: direction * distance, behavior: "smooth" });
      } else {
        strip.scrollLeft += direction * distance;
      }
      window.setTimeout(() => syncDesktopTabScrollControls(strip), 180);
    }
    function syncDesktopTabScrollControls(strip) {
      if (!strip || typeof strip.closest !== "function") return;
      const wrap = strip.closest(".project-explorer-tabs-wrap");
      if (!wrap) return;
      const leftBtn = wrap.querySelector('[data-project-tabs-scroll="left"]');
      const rightBtn = wrap.querySelector('[data-project-tabs-scroll="right"]');
      if (!leftBtn || !rightBtn) return;
      const maxScroll = Math.max(0, strip.scrollWidth - strip.clientWidth);
      const scrollLeft = Math.max(0, strip.scrollLeft || 0);
      const hasOverflow = maxScroll > 1;
      [leftBtn, rightBtn].forEach((btn) => {
        btn.classList.toggle("u-hidden", !hasOverflow);
        btn.setAttribute("aria-hidden", hasOverflow ? "false" : "true");
      });
      leftBtn.disabled = !hasOverflow || scrollLeft <= 1;
      rightBtn.disabled = !hasOverflow || scrollLeft >= maxScroll - 1;
      if (typeof syncTabStripEdges === "function") {
        syncTabStripEdges(strip, desktopTabEdgeOptions);
      }
    }
    function syncMobileTabEdges() {
      if (typeof syncTabStripEdges === "function") {
        syncTabStripEdges(ctx.projectMobileTabs, mobileTabEdgeOptions);
      }
    }
    function focusWorkspaceTab(tabId) {
      const nextTab = String(tabId || "");
      window.setTimeout(() => {
        const buttons = Array.from(ctx.projectWorkspaceModal?.querySelectorAll("[data-project-tab], [data-project-mobile-detail-tab]") || []);
        const target = buttons.find((button) => String(button.dataset.projectTab || button.dataset.projectMobileDetailTab || "") === nextTab);
        target?.focus({ preventScroll: true });
        const desktopStrip = target?.closest?.(".project-explorer-tabs");
        if (desktopStrip) syncDesktopActiveTabScroll(desktopStrip);
        syncMobileActiveTabScroll();
      }, 0);
    }
    return {
      tabCountText,
      mobileTabItems,
      renderProjectHeader,
      renderMobileDetailTopbar,
      renderMobileTabs,
      syncMobileActiveTabScroll,
      syncMobileTabEdges,
      focusWorkspaceTab
    };
  }
  const DarklabProjectNavigation = {
    createProjectNavigationController
  };
  exportedDarklabProjectNavigation = DarklabProjectNavigation;
})(globalThis);
export {
  exportedDarklabProjectNavigation as DarklabProjectNavigation
};
