import {
  exportedOpenAtlas
} from "./static-chunk-chqbks7e.9f2e150d66e2.js";
import "./static-chunk-ie6xro2m.d35c2596c34d.js";
import "./static-chunk-wkdqs5l5.75c18d0d56e7.js";
import "./static-chunk-bq2uwdee.5cc634779df5.js";
import "./static-chunk-jeg4baui.9d6201e6a078.js";
import "./static-chunk-flbvf45u.b289f40bdd3d.js";
import "./static-chunk-tda3zjlz.ba4d349f2998.js";
import "./static-chunk-ndtwds5q.291a7a432f16.js";
import "./static-chunk-rjpbqpge.4b3f5ec190f6.js";
import "./static-chunk-su3zfblw.dfaa45e2b263.js";
import "./static-chunk-xbxp24ix.e021648f87bd.js";
import {
  activeTeamScopeCan,
  teamScopeDeniedMessage
} from "./static-chunk-uwev63xf.c0c06adb18e0.js";
import "./static-chunk-poi5czx6.3f5c94749765.js";
import {
  bindDisclosure
} from "./static-chunk-zpenfczu.1862ffb66041.js";
import {
  showConfirm
} from "./static-chunk-4m44pm74.0a8001fa1d52.js";
import "./static-chunk-2bgb52uq.a327269283bb.js";
import "./static-chunk-yo5cjr7d.b86e0c93eff0.js";
import "./static-chunk-gwztcp24.e58b5ff85d88.js";
import {
  logClientError
} from "./static-chunk-2kxtimik.c9801087c7a7.js";
import "./static-chunk-4nkiwrht.8176cfb2b3d4.js";
import {
  DarklabAtlasEntityRow
} from "./static-chunk-m4e6ivjw.074a5c89d41e.js";
import "./static-chunk-6ep7jfeg.e8819f5c9afc.js";
import {
  DarklabAtlasTabs
} from "./static-chunk-y6zchygr.f5ddd7fe938a.js";

// app/static/js/features/projects/project_entities.js
var exportedDarklabProjectEntities = null;
(function initProjectEntities(global) {
  if (typeof document === "undefined") return;
  const entityRowApi = typeof DarklabAtlasEntityRow !== "undefined" && DarklabAtlasEntityRow || {};
  function _entityItems(summary) {
    return summary && Array.isArray(summary.entities) ? summary.entities : [];
  }
  function _entityTabs() {
    const atlasTabsApi = typeof DarklabAtlasTabs !== "undefined" && DarklabAtlasTabs || null;
    const atlasTabs = atlasTabsApi && Array.isArray(atlasTabsApi.tabs) ? atlasTabsApi.tabs : [
      { id: "ip", label: "Hosts/IPs", type: "ip" },
      { id: "domain", label: "Domains", type: "domain" },
      { id: "hash", label: "Hashes", type: "hash" },
      { id: "cve", label: "CVEs", type: "cve" },
      { id: "url", label: "URLs", type: "url" }
    ];
    return atlasTabs.filter((tab) => tab && tab.id !== "findings" && tab.type);
  }
  function _entityTypeLabel(type) {
    const atlasTabsApi = typeof DarklabAtlasTabs !== "undefined" && DarklabAtlasTabs || null;
    if (atlasTabsApi && typeof atlasTabsApi.labelForType === "function") {
      return atlasTabsApi.labelForType(type);
    }
    const fallback = _entityTabs().find((tab) => tab.type === String(type || ""));
    return fallback ? fallback.label : String(type || "Entity");
  }
  function _entityIntelProviders(entity) {
    const raw = entity && entity.intel_providers;
    if (Array.isArray(raw)) {
      return raw.map((provider) => String(provider || "").trim()).filter(Boolean);
    }
    return String(raw || "").split(",").map((provider) => provider.trim()).filter(Boolean);
  }
  function _entityIntelSummary(entity, formatDate) {
    const providers = _entityIntelProviders(entity);
    const count = Number(entity && entity.intel_provider_count || providers.length || 0);
    if (count <= 0) return "";
    const providerText = providers.length ? providers.slice(0, 3).join(", ") + (providers.length > 3 ? ` +${providers.length - 3}` : "") : `${count} provider${count === 1 ? "" : "s"}`;
    const refreshed = entity && entity.intel_last_refreshed ? ` · refreshed ${formatDate(entity.intel_last_refreshed)}` : "";
    return `intel: ${providerText}${refreshed}`;
  }
  function _appendDataset(el, dataset = {}) {
    Object.entries(dataset || {}).forEach(([key, value]) => {
      el.dataset[key] = value;
    });
  }
  function _fallbackProjectEntityRow({
    entity,
    projectId = "",
    title = "",
    meta = "",
    detail = "",
    chips = [],
    accessory = null,
    action = null,
    selected = false,
    checkbox = null,
    chipClass = () => "badge badge-tone-muted",
    bindPressable = null
  }) {
    const row = document.createElement("article");
    row.className = "project-explorer-item panel-row project-entity-row";
    row.classList.toggle("is-selected", !!selected);
    if (checkbox) row.appendChild(checkbox);
    let contentHost = row;
    if (action) {
      contentHost = document.createElement("button");
      contentHost.type = "button";
      contentHost.className = "control-row project-explorer-item-click-target";
      contentHost.dataset.projectAction = action.action;
      _appendDataset(contentHost, action.dataset || {});
      if (projectId && !contentHost.dataset.projectId) contentHost.dataset.projectId = projectId;
      if (typeof bindPressable === "function") bindPressable(contentHost);
    }
    const main = document.createElement("div");
    main.className = "project-explorer-item-main";
    const heading = document.createElement("div");
    heading.className = "project-explorer-item-title";
    heading.textContent = title || String(entity && (entity.canonical_value || entity.value || entity.id) || "");
    main.appendChild(heading);
    if (meta) {
      const metaEl = document.createElement("div");
      metaEl.className = "project-explorer-item-meta";
      metaEl.textContent = meta;
      main.appendChild(metaEl);
    }
    if (detail) {
      const detailEl = document.createElement("div");
      detailEl.className = "project-explorer-item-detail";
      detailEl.textContent = detail;
      main.appendChild(detailEl);
    }
    if (Array.isArray(chips) && chips.length) {
      const chipWrap = document.createElement("div");
      chipWrap.className = "project-explorer-item-chips";
      chips.forEach((chip) => {
        const chipEl = document.createElement("span");
        chipEl.className = chipClass(chip.kind);
        chipEl.textContent = String(chip.label || "");
        chipWrap.appendChild(chipEl);
      });
      main.appendChild(chipWrap);
    }
    contentHost.appendChild(main);
    if (contentHost !== row) row.appendChild(contentHost);
    if (accessory) row.appendChild(accessory);
    return row;
  }
  function _entityCounts(summary) {
    const counts = {};
    _entityTabs().forEach((tab) => {
      counts[tab.type] = 0;
    });
    _entityItems(summary).forEach((entity) => {
      const type = String(entity && entity.type || "");
      counts[type] = Number(counts[type] || 0) + 1;
    });
    return counts;
  }
  function createProjectEntitiesController(context) {
    const ctx = context || {};
    const pages = /* @__PURE__ */ new Map();
    const countPages = /* @__PURE__ */ new Map();
    const countHistory = /* @__PURE__ */ new Map();
    const countTextHistory = /* @__PURE__ */ new Map();
    const countLoads = /* @__PURE__ */ new Map();
    const pageLimit = 50;
    const ruleStates = /* @__PURE__ */ new Map();
    const targetKinds = [
      { value: "any", label: "Any" },
      { value: "domain", label: "Domain" },
      { value: "ip", label: "IP" },
      { value: "url", label: "URL" },
      { value: "cve", label: "CVE" },
      { value: "hash", label: "Hash" }
    ];
    const matchModes = [
      { value: "exact", label: "Exact" },
      { value: "contains", label: "Contains" },
      { value: "wildcard", label: "Wildcard" },
      { value: "domain_suffix", label: "Domain suffix" },
      { value: "cidr", label: "CIDR" },
      { value: "regex", label: "Regex", disabled: true }
    ];
    const domainSuffixTargetKinds = /* @__PURE__ */ new Set(["any", "domain", "url"]);
    const cidrTargetKinds = /* @__PURE__ */ new Set(["any", "ip"]);
    function activeTab() {
      return String(ctx.getActiveTab?.() || "ip");
    }
    function activeTeamScopeCan2(capability) {
      const can = typeof activeTeamScopeCan !== "undefined" && activeTeamScopeCan || null;
      return typeof can === "function" ? can(capability) : true;
    }
    function teamScopeDeniedMessage2(action) {
      const denied = typeof teamScopeDeniedMessage !== "undefined" && teamScopeDeniedMessage || null;
      return typeof denied === "function" ? denied(action) : `View-only team members can't ${action}. Switch to Personal or ask for operator access.`;
    }
    function canMutateProjects() {
      return activeTeamScopeCan2("mutate_projects");
    }
    function projectForRules(projectId) {
      const summaryProject = ctx.getSummary?.(projectId)?.project;
      if (summaryProject) return summaryProject;
      const rows = typeof ctx.projectRows === "function" ? ctx.projectRows() : [];
      return rows.find((project) => String(project && project.id || "") === String(projectId || "")) || null;
    }
    function projectRuleMutationDeniedMessage(projectId) {
      const project = projectForRules(projectId);
      if (project && typeof ctx.projectIsArchived === "function" && ctx.projectIsArchived(project)) {
        return "Archived projects are read-only.";
      }
      return teamScopeDeniedMessage2("change team projects");
    }
    function canMutateProjectRules(projectId) {
      const project = projectForRules(projectId);
      if (project && typeof ctx.projectIsArchived === "function" && ctx.projectIsArchived(project)) return false;
      return canMutateProjects();
    }
    function denyProjectMutation(projectId) {
      ctx.setProjectWorkspaceMessage?.(projectRuleMutationDeniedMessage(projectId), { error: true });
    }
    function pageKey(projectId) {
      return `${String(projectId || "")}:${activeTab()}`;
    }
    function page(projectId) {
      const key = pageKey(projectId);
      if (!pages.has(key)) pages.set(key, {
        entities: [],
        total: 0,
        countsByType: {},
        limit: pageLimit,
        offset: 0,
        filterKey: "",
        loading: false,
        loaded: false,
        error: "",
        loadSeq: 0
      });
      return pages.get(key);
    }
    function ruleState(projectId) {
      const normalizedProjectId = String(projectId || "");
      if (!ruleStates.has(normalizedProjectId)) ruleStates.set(normalizedProjectId, {
        open: false,
        loading: false,
        loaded: false,
        rules: [],
        error: "",
        editor: null,
        preview: null,
        previewKey: "",
        previewLoading: false,
        busyRuleId: "",
        filtersOpen: false
      });
      return ruleStates.get(normalizedProjectId);
    }
    function rulesPanelId(projectId) {
      const safeId = String(projectId || "active").replace(/[^a-zA-Z0-9_-]/g, "_") || "active";
      return `project-auto-promote-rules-${safeId}`;
    }
    function matchModesForTarget(targetKind) {
      const normalized = String(targetKind || "any");
      return matchModes.filter((mode) => {
        if (mode.value === "domain_suffix") return domainSuffixTargetKinds.has(normalized);
        if (mode.value === "cidr") return cidrTargetKinds.has(normalized);
        return true;
      });
    }
    function normalizeRuleEditorMatchMode(editor) {
      if (!editor) return editor;
      const available = matchModesForTarget(editor.target_entity_kind);
      if (!available.some((mode) => mode.value === editor.match_mode)) {
        const fallback = available.find((mode) => !mode.disabled) || available[0];
        editor.match_mode = fallback ? fallback.value : "exact";
      }
      return editor;
    }
    function defaultRuleEditor(projectId, rule = null) {
      const filters = rule && rule.filters && typeof rule.filters === "object" ? rule.filters : {};
      return normalizeRuleEditorMatchMode({
        projectId: String(projectId || ""),
        ruleId: String(rule && rule.id || ""),
        created: String(rule && rule.created || ""),
        name: String(rule && rule.name || ""),
        enabled: rule ? rule.enabled !== false : true,
        apply_on_run: !!(rule && rule.apply_on_run),
        target_entity_kind: String(rule && rule.target_entity_kind || "domain"),
        match_mode: String(rule && rule.match_mode || "domain_suffix"),
        pattern: String(rule && rule.pattern || ""),
        source_command_roots: Array.isArray(filters.source_command_roots) ? filters.source_command_roots.join(", ") : "",
        source_run_ids: Array.isArray(filters.source_run_ids) ? filters.source_run_ids.join(", ") : "",
        include_suppressed: !!filters.include_suppressed,
        first_seen_after_rule_created: !!filters.first_seen_after_rule_created,
        applyAfterSave: false
      });
    }
    function openAutoPromoteRuleEditor(projectId, draft = {}) {
      const normalizedProjectId = String(projectId || draft.project_id || "").trim();
      if (!normalizedProjectId) return false;
      const editor = defaultRuleEditor(normalizedProjectId, {
        name: draft.name,
        enabled: draft.enabled,
        apply_on_run: draft.apply_on_run,
        target_entity_kind: draft.target_entity_kind,
        match_mode: draft.match_mode,
        pattern: draft.pattern,
        filters: draft.filters
      });
      setRulesOpen(normalizedProjectId, true);
      setEditor(normalizedProjectId, editor);
      loadRules(normalizedProjectId).catch(() => {
      });
      ctx.setWorkspaceTab?.("entities");
      ctx.renderProjectExplorer?.();
      if (ctx.mobileView?.() === "detail") ctx.renderProjectMobileDetail?.();
      return true;
    }
    function openAutoPromoteRuleFromAtlas(projectId, draft = {}) {
      return openAutoPromoteRuleEditor(projectId, draft);
    }
    function splitCsv(value) {
      return String(value || "").split(",").map((item) => item.trim()).filter(Boolean);
    }
    function editorPayload(editor) {
      const filters = {
        source_command_roots: splitCsv(editor.source_command_roots),
        source_run_ids: splitCsv(editor.source_run_ids),
        include_suppressed: !!editor.include_suppressed,
        first_seen_after_rule_created: !!editor.first_seen_after_rule_created
      };
      const payload = {
        name: String(editor.name || "").trim(),
        enabled: !!editor.enabled,
        apply_on_run: !!editor.apply_on_run,
        target_entity_kind: String(editor.target_entity_kind || "domain"),
        match_mode: String(editor.match_mode || "domain_suffix"),
        pattern: String(editor.pattern || "").trim(),
        filters
      };
      if (editor.created) payload.created = String(editor.created);
      return payload;
    }
    function editorPreviewPayload(editor) {
      const payload = editorPayload(editor);
      delete payload.name;
      delete payload.enabled;
      delete payload.apply_on_run;
      if (!payload.filters?.first_seen_after_rule_created) delete payload.created;
      return payload;
    }
    function previewRelevantField(field) {
      return [
        "target_entity_kind",
        "match_mode",
        "pattern",
        "source_command_roots",
        "source_run_ids",
        "include_suppressed",
        "first_seen_after_rule_created"
      ].includes(String(field || ""));
    }
    function payloadKey(payload) {
      return JSON.stringify(payload || {});
    }
    function previewSummaryText(preview) {
      if (!preview) return "";
      const shown = Number(preview.shown_match_count ?? preview.matched_count ?? 0);
      const scanMatches = Number(preview.matched_in_scan_count ?? preview.total_matches ?? shown);
      const linked = Number(preview.already_linked_count || 0);
      const next = Number(preview.new_link_count || 0);
      const promoted = Number(preview.promoted_count || preview.promotable_count || 0);
      const quota = Number(preview.quota_limited_count || 0);
      const skipped = Number(preview.skipped_suppressed_count || 0);
      const scanLimited = preview.candidate_scan_truncated || Number(preview.candidate_scan_limited_count || 0);
      const scanned = Number(preview.candidate_scan_count || 0);
      const scanLimit = Number(preview.candidate_scan_limit || 0);
      const countCapped = preview.match_count_is_capped || scanMatches > shown || scanLimited;
      const matchLabel = countCapped ? "shown" : `match${shown === 1 ? "" : "es"}`;
      const parts = [
        `${shown.toLocaleString()} ${matchLabel}`,
        `${next.toLocaleString()} new`,
        `${linked.toLocaleString()} linked`
      ];
      if (!scanLimited && scanMatches > shown) parts.splice(1, 0, `${scanMatches.toLocaleString()} matches in scan`);
      if (promoted) parts.splice(2, 0, `${promoted.toLocaleString()} promoted`);
      if (quota) parts.push(`${quota.toLocaleString()} quota-limited`);
      if (skipped) parts.push(`${skipped.toLocaleString()} suppressed skipped`);
      if (scanLimited) parts.push(`scanned first ${(scanned || scanLimit).toLocaleString()} candidates`);
      if (preview.truncated || Number(preview.match_cap_limited_count || 0)) parts.push("limited");
      return parts.join(" · ");
    }
    function setPageOffset(projectId, offset = 0) {
      const state = page(projectId);
      state.offset = Math.max(0, Number(offset || 0));
      state.limit = pageLimit;
      state.loading = true;
      state.loaded = false;
    }
    function appendEntityFilters(params, projectId) {
      const normalizedProjectId = String(projectId || "");
      const summary = ctx.getSummary?.(normalizedProjectId);
      const targetFilters = typeof ctx.projectTargetFilterSet === "function" ? ctx.projectTargetFilterSet(normalizedProjectId) : /* @__PURE__ */ new Set();
      const targets = typeof ctx.projectTargetItems === "function" ? ctx.projectTargetItems(summary) : [];
      const availableTargets = new Set(
        (Array.isArray(targets) ? targets : []).map((target) => String(target && target.id || "")).filter(Boolean)
      );
      targetFilters.forEach((targetId) => {
        if (targetId && availableTargets.has(targetId)) params.append("target_id", targetId);
      });
      const runFilters = typeof ctx.projectRunFilterSet === "function" ? ctx.projectRunFilterSet(normalizedProjectId) : /* @__PURE__ */ new Set();
      runFilters.forEach((runId) => {
        if (runId) params.append("run_id", runId);
      });
    }
    function entityFilterScopeKey(projectId) {
      const params = new URLSearchParams();
      appendEntityFilters(params, projectId);
      params.sort?.();
      return params.toString();
    }
    function entityFiltersActive(projectId) {
      return !!entityFilterScopeKey(projectId);
    }
    function entityFilterParams(projectId, state) {
      const normalizedProjectId = String(projectId || "");
      const pageState = state || page(normalizedProjectId);
      const params = new URLSearchParams({
        limit: String(pageState.limit || pageLimit),
        offset: String(pageState.offset || 0)
      });
      const type = activeType();
      if (type) params.set("type", type);
      appendEntityFilters(params, normalizedProjectId);
      params.sort?.();
      return params;
    }
    function resetPages() {
      pages.clear();
      countPages.clear();
      countHistory.clear();
      countTextHistory.clear();
      countLoads.clear();
    }
    function linkedIds(projectId) {
      const normalized = String(projectId || "");
      const summary = ctx.getSummary?.(normalized);
      return new Set(
        (Array.isArray(summary?.links) ? summary.links : []).filter((link) => String(link && link.entity_type || "") === "atlas_entity").map((link) => String(link && link.entity_id || "")).filter(Boolean)
      );
    }
    function invalidate(projectId = "") {
      const normalized = String(projectId || "");
      if (!normalized) {
        pages.clear();
        countPages.clear();
        countHistory.clear();
        countTextHistory.clear();
        countLoads.clear();
        return;
      }
      [...pages.keys()].forEach((key) => {
        if (key.startsWith(`${normalized}:`)) pages.delete(key);
      });
      countPages.delete(normalized);
      [...countLoads.keys()].forEach((key) => {
        if (key.startsWith(`${normalized}:`)) countLoads.delete(key);
      });
    }
    function rememberedCountText(projectId, scopeKey, type) {
      return countTextHistory.get(String(projectId || ""))?.get(`${scopeKey}:${type}`) || "";
    }
    function rememberCountText(projectId, scopeKey, type, text) {
      const normalizedProjectId = String(projectId || "");
      if (!normalizedProjectId || !scopeKey || !type) return;
      if (!countTextHistory.has(normalizedProjectId)) countTextHistory.set(normalizedProjectId, /* @__PURE__ */ new Map());
      countTextHistory.get(normalizedProjectId).set(`${scopeKey}:${type}`, String(text || ""));
    }
    function rememberCountPage(projectId, entry) {
      const normalizedProjectId = String(projectId || "");
      if (!normalizedProjectId || !entry || !entry.key) return;
      countPages.set(normalizedProjectId, entry);
      if (!countHistory.has(normalizedProjectId)) countHistory.set(normalizedProjectId, /* @__PURE__ */ new Map());
      countHistory.get(normalizedProjectId).set(entry.key, entry.countsByType || {});
    }
    function countPageForScope(projectId) {
      const normalizedProjectId = String(projectId || "");
      const scopeKey = entityFilterScopeKey(normalizedProjectId);
      const cached = countPages.get(normalizedProjectId);
      if (cached && cached.key === scopeKey) return cached.countsByType || {};
      const historicalCounts = countHistory.get(normalizedProjectId)?.get(scopeKey);
      return historicalCounts || null;
    }
    function selectedIds() {
      return ctx.getSelectedIds?.() || /* @__PURE__ */ new Set();
    }
    function pickerState() {
      return ctx.getPicker?.() || null;
    }
    function setPickerState(nextState) {
      ctx.setPicker?.(nextState || null);
    }
    function selectMode() {
      return !!ctx.getSelectMode?.();
    }
    function items(summary) {
      const projectId = String(summary?.project?.id || ctx.getSelectedProjectId?.() || "");
      return page(projectId).entities || _entityItems(summary);
    }
    function tabs() {
      return _entityTabs();
    }
    function typeLabel(type) {
      return _entityTypeLabel(type);
    }
    function intelSummary(entity) {
      return _entityIntelSummary(entity, ctx.formatDate || ((value) => String(value || "")));
    }
    function counts(summary) {
      const projectId = String(summary?.project?.id || ctx.getSelectedProjectId?.() || "");
      const cachedCounts = countPageForScope(projectId);
      if (cachedCounts) return cachedCounts;
      return summary && summary.entity_counts && typeof summary.entity_counts === "object" ? summary.entity_counts : _entityCounts(summary);
    }
    function totalCounts(summary) {
      return summary && summary.entity_counts && typeof summary.entity_counts === "object" ? summary.entity_counts : _entityCounts(summary);
    }
    function typeCountText(projectId, summary, type) {
      const total = Number(totalCounts(summary)[type] || 0);
      if (!entityFiltersActive(projectId)) return total.toLocaleString();
      const scopeKey = entityFilterScopeKey(projectId);
      ensureFilteredCounts(projectId);
      const countsByType = countPageForScope(projectId);
      if (!countsByType) {
        const remembered = rememberedCountText(projectId, scopeKey, type);
        if (remembered) return remembered;
        return `${total.toLocaleString()}/${total.toLocaleString()}`;
      }
      const filtered = Number(countsByType[type] || 0);
      const text = `${filtered.toLocaleString()}/${total.toLocaleString()}`;
      rememberCountText(projectId, scopeKey, type, text);
      return text;
    }
    function tabCountText(projectId, summary, total) {
      const totalCount = Number(total || summary?.counts?.entities || 0);
      if (!entityFiltersActive(projectId)) return totalCount.toLocaleString();
      const scopeKey = entityFilterScopeKey(projectId);
      ensureFilteredCounts(projectId);
      const countsByType = countPageForScope(projectId);
      if (!countsByType) {
        const remembered = rememberedCountText(projectId, scopeKey, "__all__");
        if (remembered) return remembered;
        return `${totalCount.toLocaleString()}/${totalCount.toLocaleString()}`;
      }
      const filtered = Object.values(countsByType).reduce((sum, count) => sum + Number(count || 0), 0);
      const text = `${filtered.toLocaleString()}/${totalCount.toLocaleString()}`;
      rememberCountText(projectId, scopeKey, "__all__", text);
      return text;
    }
    function activeType() {
      const currentTabs = tabs();
      const current = currentTabs.find((tab) => tab.id === activeTab()) || currentTabs[0] || { type: "" };
      return current.type || "";
    }
    function itemsForActiveTab(summary) {
      const projectId = String(summary?.project?.id || ctx.getSelectedProjectId?.() || "");
      return page(projectId).entities || [];
    }
    function pagedItemsForActiveTab(projectId) {
      return page(projectId).entities || [];
    }
    function ensureFilteredCounts(projectId) {
      const normalizedProjectId = String(projectId || ctx.getSelectedProjectId?.() || "");
      if (!normalizedProjectId || !entityFiltersActive(normalizedProjectId)) return null;
      const scopeKey = entityFilterScopeKey(normalizedProjectId);
      const cached = countPages.get(normalizedProjectId);
      if (cached && cached.key === scopeKey) return cached;
      const loadKey = `${normalizedProjectId}:${scopeKey}`;
      if (countLoads.has(loadKey)) return countLoads.get(loadKey);
      const params = new URLSearchParams({ limit: "1", offset: "0" });
      appendEntityFilters(params, normalizedProjectId);
      params.sort?.();
      const request = ctx.apiFetch(`/projects/${encodeURIComponent(normalizedProjectId)}/entities?${params.toString()}`, {
        cache: "no-store"
      }).then(async (resp) => {
        if (!resp.ok) throw await ctx.projectResponseError(resp, "Could not load project entity counts.");
        const data = await resp.json();
        if (entityFilterScopeKey(normalizedProjectId) !== scopeKey) return null;
        const next = {
          key: scopeKey,
          countsByType: data.counts_by_type && typeof data.counts_by_type === "object" ? data.counts_by_type : {}
        };
        rememberCountPage(normalizedProjectId, next);
        ctx.renderProjectExplorer?.();
        if (ctx.mobileView?.() === "detail") ctx.renderProjectMobileDetail?.();
        return next;
      }).catch((err) => {
        if (typeof ctx.logClientError === "function") ctx.logClientError("failed to load project entity counts", err);
        return null;
      }).finally(() => {
        countLoads.delete(loadKey);
      });
      countLoads.set(loadKey, request);
      return request;
    }
    async function load(projectId, options = {}) {
      const normalizedProjectId = String(projectId || ctx.getSelectedProjectId?.() || "");
      if (!normalizedProjectId) return null;
      const state = page(normalizedProjectId);
      if (Object.prototype.hasOwnProperty.call(options, "offset")) {
        state.offset = Math.max(0, Number(options.offset || 0));
      }
      state.limit = pageLimit;
      state.loading = true;
      state.error = "";
      const requestKey = pageKey(normalizedProjectId);
      const requestId = Number(state.loadSeq || 0) + 1;
      state.loadSeq = requestId;
      const isStale = () => pageKey(normalizedProjectId) !== requestKey || page(normalizedProjectId) !== state || state.loadSeq !== requestId;
      const params = entityFilterParams(normalizedProjectId, state);
      const type = activeType();
      const nextFilterKey = params.toString();
      const nextScopeKey = entityFilterScopeKey(normalizedProjectId);
      try {
        const resp = await ctx.apiFetch(`/projects/${encodeURIComponent(normalizedProjectId)}/entities?${params.toString()}`, {
          cache: "no-store"
        });
        if (!resp.ok) throw await ctx.projectResponseError(resp, "Could not load project entities.");
        const data = await resp.json();
        if (isStale()) return state;
        state.entities = Array.isArray(data.entities) ? data.entities : [];
        state.total = Number(data.total || 0);
        state.limit = Number(data.limit || pageLimit);
        state.offset = Number(data.offset || 0);
        state.countsByType = data.counts_by_type && typeof data.counts_by_type === "object" ? data.counts_by_type : {};
        state.filterKey = nextFilterKey;
        if (!entityFiltersActive(normalizedProjectId)) {
          rememberCountPage(normalizedProjectId, {
            key: nextScopeKey,
            countsByType: state.countsByType
          });
        }
        const fallbackSummary = ctx.getSummary?.(normalizedProjectId);
        const fallbackEntities = _entityItems(fallbackSummary).filter((entity) => !type || String(entity && entity.type || "") === type);
        if (!entityFiltersActive(normalizedProjectId) && !state.entities.length && fallbackEntities.length) {
          state.entities = fallbackEntities.slice(state.offset, state.offset + state.limit);
          state.total = fallbackEntities.length;
          state.countsByType = _entityCounts(fallbackSummary);
          rememberCountPage(normalizedProjectId, {
            key: nextScopeKey,
            countsByType: state.countsByType
          });
        }
        state.loaded = true;
        return state;
      } catch (err) {
        if (isStale()) return state;
        state.error = err && err.message ? err.message : "Could not load project entities.";
        ctx.setProjectWorkspaceMessage?.(state.error, { error: true });
        if (typeof ctx.logClientError === "function") ctx.logClientError("failed to load project entities", err);
        return state;
      } finally {
        if (state.loadSeq === requestId) state.loading = false;
        if (!isStale() && !options.skipFinalRender) {
          ctx.renderProjectExplorer?.();
          if (ctx.mobileView?.() === "detail") ctx.renderProjectMobileDetail?.();
        }
      }
    }
    function byId(summary, entityId) {
      const normalized = String(entityId || "").trim();
      if (!normalized) return null;
      const projectId = String(summary?.project?.id || ctx.getSelectedProjectId?.() || "");
      return (page(projectId).entities || []).find((item) => String(item && item.id || "") === normalized) || null;
    }
    function chips(entity) {
      const chipItems = ctx.entityMetadataChips?.(entity) || [];
      const source = String(entity && entity.source || "");
      const detail = entity && entity.source_detail && typeof entity.source_detail === "object" ? entity.source_detail : {};
      if (source === "auto_promote_rule") {
        const ruleName = String(detail.rule_name || "").trim();
        chipItems.push({ label: ruleName ? `Auto-promoted: ${ruleName}` : "Auto-promoted", kind: "note" });
      }
      const intelCount = Number(entity && entity.intel_provider_count || 0);
      if (intelCount > 0) {
        const providers = _entityIntelProviders(entity);
        if (providers.length) {
          providers.slice(0, 3).forEach((provider) => chipItems.push({ label: provider, kind: "label" }));
          if (providers.length > 3) chipItems.push({ label: `+${providers.length - 3} providers`, kind: "label" });
        } else {
          chipItems.push({ label: `intel: ${intelCount} provider${intelCount === 1 ? "" : "s"}`, kind: "label" });
        }
      }
      const runCount = Number(entity && entity.run_count || 0);
      if (runCount > 0) {
        chipItems.push({ label: `${runCount} run${runCount === 1 ? "" : "s"}`, kind: "note" });
      }
      return chipItems;
    }
    function rulePatternSummary(rule) {
      const target = String(rule && rule.target_entity_kind || "any");
      const mode = String(rule && rule.match_mode || "");
      const pattern = String(rule && rule.pattern || "");
      return `${target} · ${mode.replace(/_/g, " ")} · ${pattern}`;
    }
    function logAutoPromoteClientError(action, projectId, err, ruleId = "") {
      if (typeof ctx.logClientError !== "function") return;
      const safeProjectId = String(projectId || "");
      const safeRuleId = String(ruleId || "");
      const parts = [`project auto-promote rule ${action} failed`, `project_id=${safeProjectId}`];
      if (safeRuleId) parts.push(`rule_id=${safeRuleId}`);
      ctx.logClientError(parts.join(" "), err);
    }
    function renderProjectExplorerSafe(action, projectId, ruleId = "") {
      try {
        ctx.renderProjectExplorer?.();
      } catch (err) {
        logAutoPromoteClientError(action, projectId, err, ruleId);
      }
    }
    function ruleDetail(rule) {
      const parts = [];
      if (rule && rule.enabled === false) parts.push("disabled");
      else parts.push("enabled");
      parts.push(rule && rule.apply_on_run ? "applies to new runs" : "manual apply");
      if (rule && rule.last_applied_at) parts.push(`last applied ${ctx.formatDate(rule.last_applied_at)}`);
      const linked = Number(rule && rule.linked_count || 0);
      if (linked) parts.push(`${linked.toLocaleString()} linked last apply`);
      return parts.join(" · ");
    }
    async function loadRules(projectId, { force = false } = {}) {
      const state = ruleState(projectId);
      if (!projectId || state.loading || state.loaded && !force) return state;
      state.loading = true;
      state.error = "";
      ctx.renderProjectExplorer?.();
      try {
        const resp = await ctx.apiFetch(`/projects/${encodeURIComponent(projectId)}/auto-promote-rules`, {
          cache: "no-store"
        });
        if (!resp.ok) throw await ctx.projectResponseError(resp, "Could not load auto-promote rules.");
        const data = await resp.json();
        state.rules = Array.isArray(data.rules) ? data.rules : [];
        state.loaded = true;
      } catch (err) {
        state.error = err && err.message ? err.message : "Could not load auto-promote rules.";
        ctx.setProjectWorkspaceMessage?.(state.error, { error: true });
        logAutoPromoteClientError("list", projectId, err);
      } finally {
        state.loading = false;
        ctx.renderProjectExplorer?.();
        if (ctx.mobileView?.() === "detail") ctx.renderProjectMobileDetail?.();
      }
      return state;
    }
    async function previewRuleRequest(projectId, payload) {
      const resp = await ctx.apiFetch(`/projects/${encodeURIComponent(projectId)}/auto-promote-rules/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {})
      });
      if (!resp.ok) throw await ctx.projectResponseError(resp, "Could not preview auto-promote rule.");
      return resp;
    }
    function setRulesOpen(projectId, open) {
      const state = ruleState(projectId);
      state.open = !!open;
      if (state.open && !state.loaded && !state.loading) loadRules(projectId).catch(() => {
      });
    }
    function setEditor(projectId, editor) {
      const state = ruleState(projectId);
      state.editor = editor;
      state.preview = null;
      state.previewKey = "";
    }
    async function previewEditorRule(projectId) {
      const state = ruleState(projectId);
      if (!state.editor) return null;
      const payload = editorPayload(state.editor);
      const previewKey = payloadKey(editorPreviewPayload(state.editor));
      state.previewLoading = true;
      state.preview = null;
      state.previewKey = "";
      const previewRequest = previewRuleRequest(projectId, payload);
      try {
        await Promise.resolve();
        renderProjectExplorerSafe("preview render", projectId, state.editor?.ruleId || "");
        const resp = await previewRequest;
        const data = await resp.json().catch(() => ({}));
        state.preview = data.preview || null;
        state.previewKey = previewKey;
        return state.preview;
      } catch (err) {
        ctx.setProjectWorkspaceMessage?.(err && err.message ? err.message : "Could not preview auto-promote rule.", {
          error: true
        });
        logAutoPromoteClientError("preview", projectId, err, state.editor?.ruleId || "");
        return null;
      } finally {
        state.previewLoading = false;
        renderProjectExplorerSafe("preview final render", projectId, state.editor?.ruleId || "");
      }
    }
    async function confirmApplyRule(rule, preview) {
      const confirmFn = typeof ctx.showConfirm === "function" ? ctx.showConfirm : typeof showConfirm !== "undefined" && showConfirm || null;
      if (!confirmFn) return true;
      const choice = await confirmFn({
        body: {
          text: `Apply "${String(rule && rule.name || "this rule")}" to existing Atlas entities?`,
          note: previewSummaryText(preview)
        },
        actions: [
          { id: "cancel", label: "Cancel", role: "cancel" },
          { id: "apply", label: "Apply", role: "primary" }
        ]
      });
      return choice === "apply";
    }
    async function confirmDeleteRule(rule) {
      const confirmFn = typeof ctx.showConfirm === "function" ? ctx.showConfirm : typeof showConfirm !== "undefined" && showConfirm || null;
      if (!confirmFn) return true;
      const choice = await confirmFn({
        body: {
          text: `Delete "${String(rule && rule.name || "this rule")}"?`,
          note: "Existing promoted links stay in the project."
        },
        tone: "danger",
        actions: [
          { id: "cancel", label: "Cancel", role: "cancel" },
          { id: "delete", label: "Delete", role: "destructive" }
        ]
      });
      return choice === "delete";
    }
    async function previewStoredRule(projectId, rule) {
      const resp = await previewRuleRequest(projectId, rule);
      const data = await resp.json().catch(() => ({}));
      return data.preview || null;
    }
    async function applyStoredRule(projectId, rule) {
      if (!canMutateProjectRules(projectId)) {
        denyProjectMutation(projectId);
        return;
      }
      const state = ruleState(projectId);
      const ruleId = String(rule && rule.id || "");
      if (!ruleId) return;
      state.busyRuleId = ruleId;
      ctx.renderProjectExplorer?.();
      try {
        const preview = await previewStoredRule(projectId, rule);
        const confirmed = await confirmApplyRule(rule, preview);
        if (!confirmed) return;
        const resp = await ctx.projectWorkspaceRequest(
          `/projects/${encodeURIComponent(projectId)}/auto-promote-rules/${encodeURIComponent(ruleId)}/apply`,
          { method: "POST" }
        );
        const data = await resp.json().catch(() => ({}));
        const result = data.result || {};
        await loadRules(projectId, { force: true });
        await load(projectId, { offset: page(projectId).offset, skipFinalRender: true });
        await ctx.refreshProjectWorkspace?.();
        ctx.setProjectWorkspaceMessage?.(`Auto-promote applied: ${previewSummaryText(result)}.`);
      } catch (err) {
        ctx.setProjectWorkspaceMessage?.(err && err.message ? err.message : "Could not apply auto-promote rule.", {
          error: true
        });
        logAutoPromoteClientError("apply", projectId, err, ruleId);
      } finally {
        state.busyRuleId = "";
        ctx.renderProjectExplorer?.();
      }
    }
    async function deleteStoredRule(projectId, rule) {
      if (!canMutateProjectRules(projectId)) {
        denyProjectMutation(projectId);
        return;
      }
      const ruleId = String(rule && rule.id || "");
      if (!ruleId) return;
      const confirmed = await confirmDeleteRule(rule);
      if (!confirmed) return;
      const state = ruleState(projectId);
      state.busyRuleId = ruleId;
      ctx.renderProjectExplorer?.();
      try {
        await ctx.projectWorkspaceRequest(
          `/projects/${encodeURIComponent(projectId)}/auto-promote-rules/${encodeURIComponent(ruleId)}`,
          { method: "DELETE" }
        );
        await loadRules(projectId, { force: true });
        ctx.setProjectWorkspaceMessage?.("Auto-promote rule deleted.");
      } catch (err) {
        ctx.setProjectWorkspaceMessage?.(err && err.message ? err.message : "Could not delete auto-promote rule.", {
          error: true
        });
        logAutoPromoteClientError("delete", projectId, err, ruleId);
      } finally {
        state.busyRuleId = "";
        ctx.renderProjectExplorer?.();
      }
    }
    async function saveEditorRule(projectId) {
      if (!canMutateProjectRules(projectId)) {
        denyProjectMutation(projectId);
        return;
      }
      const state = ruleState(projectId);
      const editor = state.editor;
      if (!editor) return;
      const payload = editorPayload(editor);
      const currentKey = payloadKey(editorPreviewPayload(editor));
      if (editor.enabled !== false && state.previewKey !== currentKey) {
        ctx.setProjectWorkspaceMessage?.("Preview the rule before saving.", { error: true });
        return;
      }
      const isUpdate = !!editor.ruleId;
      state.busyRuleId = editor.ruleId || "__new__";
      try {
        const saveRequest = ctx.projectWorkspaceRequest(
          isUpdate ? `/projects/${encodeURIComponent(projectId)}/auto-promote-rules/${encodeURIComponent(editor.ruleId)}` : `/projects/${encodeURIComponent(projectId)}/auto-promote-rules`,
          {
            method: isUpdate ? "PUT" : "POST",
            body: JSON.stringify(payload)
          }
        );
        renderProjectExplorerSafe("save render", projectId, editor.ruleId || "");
        const resp = await saveRequest;
        const data = await resp.json().catch(() => ({}));
        const savedRule = data.rule || { ...payload, id: editor.ruleId };
        if (editor.applyAfterSave && savedRule.enabled !== false) {
          const savedPreview = await previewStoredRule(projectId, savedRule);
          const confirmed = await confirmApplyRule(savedRule, savedPreview);
          if (confirmed) {
            const applyResp = await ctx.projectWorkspaceRequest(
              `/projects/${encodeURIComponent(projectId)}/auto-promote-rules/${encodeURIComponent(savedRule.id)}/apply`,
              { method: "POST" }
            );
            const applyData = await applyResp.json().catch(() => ({}));
            await ctx.refreshProjectWorkspace?.();
            ctx.setProjectWorkspaceMessage?.(`Auto-promote rule saved and applied: ${previewSummaryText(applyData.result)}.`);
          } else {
            ctx.setProjectWorkspaceMessage?.("Auto-promote rule saved.");
          }
        } else {
          ctx.setProjectWorkspaceMessage?.("Auto-promote rule saved.");
        }
        state.editor = null;
        state.preview = null;
        state.previewKey = "";
        await loadRules(projectId, { force: true });
        await load(projectId, { offset: page(projectId).offset, skipFinalRender: true });
      } catch (err) {
        ctx.setProjectWorkspaceMessage?.(err && err.message ? err.message : "Could not save auto-promote rule.", {
          error: true
        });
        logAutoPromoteClientError("save", projectId, err, editor.ruleId || "");
      } finally {
        state.busyRuleId = "";
        renderProjectExplorerSafe("save final render", projectId, editor.ruleId || "");
      }
    }
    function rowAccessory(projectId, entity) {
      const entityId = String(entity && entity.id || "");
      const value = String(entity && (entity.canonical_value || entity.value) || "");
      const type = String(entity && entity.type || "");
      const wrap = document.createElement("div");
      wrap.className = "project-entity-row-actions";
      const open = ctx.makeProjectButton("Open in Atlas", "open-project-entity", projectId);
      open.dataset.entityId = entityId;
      open.dataset.entityValue = value;
      open.dataset.entityType = type;
      const unlink = ctx.makeProjectButton("Unlink", "unlink-project-entity", projectId, "destructive");
      unlink.dataset.entityId = entityId;
      unlink.dataset.entityValue = value;
      wrap.append(open, unlink);
      return wrap;
    }
    function renderTypeTabs(projectId, summary) {
      const wrap = document.createElement("div");
      wrap.className = "project-entity-type-tabs tab-strip";
      wrap.setAttribute("role", "tablist");
      wrap.setAttribute("aria-label", "Project entity types");
      tabs().forEach((tab) => {
        const btn = document.createElement("button");
        btn.type = "button";
        const active = activeTab() === tab.id;
        btn.className = "tab-strip-item project-entity-type-tab" + (active ? " is-active" : "");
        btn.dataset.projectEntityTab = tab.id;
        btn.dataset.projectId = projectId;
        btn.setAttribute("role", "tab");
        btn.setAttribute("aria-selected", active ? "true" : "false");
        btn.setAttribute("aria-pressed", active ? "true" : "false");
        const label = document.createElement("span");
        label.className = "project-entity-type-tab-label";
        label.textContent = tab.label;
        const count = document.createElement("span");
        count.className = "project-entity-type-tab-count";
        count.textContent = typeCountText(projectId, summary, tab.type);
        btn.append(label, count);
        ctx.bindProjectRuntimePressable?.(btn);
        wrap.appendChild(btn);
      });
      return wrap;
    }
    function renderToolbar(projectId, visibleEntities) {
      const toolbar = document.createElement("div");
      toolbar.className = "project-entity-toolbar";
      const actions = document.createElement("div");
      actions.className = "project-entity-toolbar-actions";
      const rules = ctx.makeProjectButton("Rules", "toggle-project-auto-promote-rules", projectId);
      rules.classList.add("project-auto-promote-rules-toggle");
      rules.setAttribute("aria-expanded", ruleState(projectId).open ? "true" : "false");
      rules.setAttribute("aria-controls", rulesPanelId(projectId));
      actions.append(
        ctx.makeProjectButton("Add entity", "open-entity-picker", projectId, "primary"),
        rules,
        ctx.makeProjectButton("Export CSV", "export-project-entities-csv", projectId),
        ctx.makeProjectButton("Export JSONL", "export-project-entities-jsonl", projectId)
      );
      const select = document.createElement("div");
      select.className = "project-entity-select-actions";
      const toggle = ctx.makeProjectButton(selectMode() ? "Done" : "Select", "toggle-project-entity-select", projectId);
      if (!selectMode() && !activeTeamScopeCan2("mutate_projects")) {
        toggle.disabled = true;
        toggle.title = teamScopeDeniedMessage2("change team projects");
      }
      select.appendChild(toggle);
      if (selectMode()) {
        const currentSelected = selectedIds();
        const count = document.createElement("span");
        count.className = "project-entity-selection-count";
        count.setAttribute("aria-live", "polite");
        count.textContent = `${currentSelected.size} selected`;
        const selectAll = ctx.makeProjectButton("Select all", "select-all-project-entities", projectId);
        selectAll.disabled = !visibleEntities.length;
        const clear = ctx.makeProjectButton("Clear", "clear-project-entities", projectId);
        clear.disabled = !currentSelected.size;
        const unlink = ctx.makeProjectButton("Unlink", "bulk-unlink-project-entities", projectId, "destructive");
        unlink.disabled = !currentSelected.size;
        select.append(count, selectAll, clear, unlink);
      }
      toolbar.append(actions, select);
      return toolbar;
    }
    function renderRuleSelect(name, value, options, disabled) {
      const select = document.createElement("select");
      select.className = "form-select project-auto-promote-field";
      select.dataset.projectAutoPromoteField = name;
      select.disabled = !!disabled;
      options.forEach((item) => {
        const option = document.createElement("option");
        option.value = item.value;
        option.textContent = item.label;
        option.selected = item.value === value;
        option.disabled = !!item.disabled;
        select.appendChild(option);
      });
      return select;
    }
    function renderRuleField(labelText, control) {
      const label = document.createElement("label");
      label.className = "project-auto-promote-field-wrap";
      const text = document.createElement("span");
      text.textContent = labelText;
      label.append(text, control);
      return label;
    }
    function renderRuleCheckbox(labelText, field, checked, disabled = false) {
      const label = document.createElement("label");
      label.className = "form-check project-auto-promote-check";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.dataset.projectAutoPromoteField = field;
      input.checked = !!checked;
      input.disabled = !!disabled;
      const text = document.createElement("span");
      text.textContent = labelText;
      label.append(input, text);
      return label;
    }
    function renderRuleEditor(projectId, state) {
      const editor = state.editor;
      if (!editor) return null;
      normalizeRuleEditorMatchMode(editor);
      const disabled = !canMutateProjectRules(projectId) || !!state.busyRuleId;
      const currentPayloadKey = payloadKey(editorPreviewPayload(editor));
      const requiresPreview = editor.enabled !== false;
      const previewCurrent = !requiresPreview || state.previewKey === currentPayloadKey;
      const canAttemptSave = !state.previewLoading && !state.busyRuleId;
      const availableMatchModes = matchModesForTarget(editor.target_entity_kind);
      const card = document.createElement("form");
      card.className = "project-auto-promote-editor panel-row";
      card.dataset.projectAutoPromoteEditor = "1";
      card.dataset.projectId = projectId;
      card.addEventListener("submit", (event) => {
        event.preventDefault();
      });
      const title = document.createElement("div");
      title.className = "project-auto-promote-editor-title";
      title.textContent = editor.ruleId ? "Edit rule" : "New rule";
      const grid = document.createElement("div");
      grid.className = "project-auto-promote-editor-grid";
      const name = document.createElement("input");
      name.className = "form-control project-auto-promote-field";
      name.dataset.projectAutoPromoteField = "name";
      name.value = editor.name;
      name.maxLength = 120;
      name.disabled = disabled;
      const pattern = document.createElement("input");
      pattern.className = "form-control project-auto-promote-field";
      pattern.dataset.projectAutoPromoteField = "pattern";
      pattern.value = editor.pattern;
      pattern.maxLength = 500;
      pattern.disabled = disabled;
      grid.append(
        renderRuleField("Name", name),
        renderRuleField("Entity kind", renderRuleSelect("target_entity_kind", editor.target_entity_kind, targetKinds, disabled)),
        renderRuleField("Match mode", renderRuleSelect("match_mode", editor.match_mode, availableMatchModes, disabled)),
        renderRuleField("Pattern", pattern)
      );
      const toggles = document.createElement("div");
      toggles.className = "project-auto-promote-toggle-row";
      toggles.append(
        renderRuleCheckbox("Enabled", "enabled", editor.enabled, disabled),
        renderRuleCheckbox("Apply automatically to new runs", "apply_on_run", editor.apply_on_run, disabled),
        renderRuleCheckbox("Apply to existing entities after save", "applyAfterSave", editor.applyAfterSave, disabled)
      );
      const filters = document.createElement("div");
      filters.className = "project-auto-promote-filters";
      const filterTrigger = document.createElement("button");
      filterTrigger.type = "button";
      filterTrigger.className = "control-row project-auto-promote-filters-trigger";
      filterTrigger.textContent = "Optional filters";
      const filterPanel = document.createElement("div");
      filterPanel.className = "project-auto-promote-filters-panel";
      filterPanel.hidden = !state.filtersOpen;
      filters.append(filterTrigger, filterPanel);
      const filterGrid = document.createElement("div");
      filterGrid.className = "project-auto-promote-editor-grid";
      const commandRoots = document.createElement("input");
      commandRoots.className = "form-control project-auto-promote-field";
      commandRoots.dataset.projectAutoPromoteField = "source_command_roots";
      commandRoots.value = editor.source_command_roots;
      commandRoots.disabled = disabled;
      const runIds = document.createElement("input");
      runIds.className = "form-control project-auto-promote-field";
      runIds.dataset.projectAutoPromoteField = "source_run_ids";
      runIds.value = editor.source_run_ids;
      runIds.disabled = disabled;
      filterGrid.append(
        renderRuleField("Command roots", commandRoots),
        renderRuleField("Source run IDs", runIds)
      );
      const filterChecks = document.createElement("div");
      filterChecks.className = "project-auto-promote-toggle-row";
      filterChecks.append(
        renderRuleCheckbox("Include suppressed entities", "include_suppressed", editor.include_suppressed, disabled),
        renderRuleCheckbox("Only first seen after rule creation", "first_seen_after_rule_created", editor.first_seen_after_rule_created, disabled)
      );
      filterPanel.append(filterGrid, filterChecks);
      const bindDisclosureFn = typeof bindDisclosure !== "undefined" && bindDisclosure || null;
      if (bindDisclosureFn) {
        bindDisclosureFn(filterTrigger, {
          panel: filterPanel,
          hiddenClass: "u-hidden",
          openClass: "is-open",
          initialOpen: state.filtersOpen,
          stopPropagation: true,
          onToggle: (open) => {
            state.filtersOpen = !!open;
            filterPanel.hidden = !open;
          }
        });
      } else {
        filterTrigger.setAttribute("aria-expanded", state.filtersOpen ? "true" : "false");
        filterTrigger.addEventListener("click", () => {
          state.filtersOpen = !state.filtersOpen;
          filterTrigger.setAttribute("aria-expanded", state.filtersOpen ? "true" : "false");
          filterPanel.hidden = !state.filtersOpen;
        });
      }
      const preview = document.createElement("div");
      preview.className = "project-auto-promote-preview";
      preview.setAttribute("aria-live", "polite");
      if (state.previewLoading) {
        preview.textContent = "Previewing...";
      } else if (state.preview) {
        preview.textContent = previewSummaryText(state.preview);
      } else if (!requiresPreview) {
        preview.textContent = "Disabled rules can be saved without preview.";
      } else {
        preview.textContent = "Preview required before save.";
      }
      const actions = document.createElement("div");
      actions.className = "project-auto-promote-editor-actions";
      const previewBtn = ctx.makeProjectButton("Preview", "preview-project-auto-promote-rule", projectId);
      previewBtn.disabled = disabled || state.previewLoading || !requiresPreview;
      const cancel = ctx.makeProjectButton("Cancel", "cancel-project-auto-promote-rule", projectId);
      const save = ctx.makeProjectButton(editor.ruleId ? "Save rule" : "Create rule", "save-project-auto-promote-rule", projectId, "primary");
      save.disabled = disabled || !canAttemptSave;
      if (!previewCurrent) save.title = "Preview the rule before saving.";
      previewBtn.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        void previewEditorRule(projectId);
      }, { capture: true });
      cancel.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        setEditor(projectId, null);
        ctx.renderProjectExplorer?.();
      }, { capture: true });
      save.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        void saveEditorRule(projectId);
      }, { capture: true });
      actions.append(previewBtn, cancel, save);
      card.append(title, grid, toggles, filters, preview, actions);
      return card;
    }
    function renderRulesPanel(projectId) {
      const state = ruleState(projectId);
      if (!state.open) return null;
      if (!state.loaded && !state.loading) loadRules(projectId).catch(() => {
      });
      const panel = document.createElement("section");
      panel.className = "project-auto-promote-panel";
      panel.id = rulesPanelId(projectId);
      panel.setAttribute("aria-label", "Auto-promote rules");
      const header = document.createElement("div");
      header.className = "project-auto-promote-header";
      const title = document.createElement("div");
      title.className = "project-auto-promote-title";
      title.textContent = "Auto-promote rules";
      const actions = document.createElement("div");
      actions.className = "project-auto-promote-actions";
      const refresh = ctx.makeProjectButton("Refresh", "refresh-project-auto-promote-rules", projectId);
      const create = ctx.makeProjectButton("New rule", "new-project-auto-promote-rule", projectId, "primary");
      if (!canMutateProjectRules(projectId)) {
        create.disabled = true;
        create.title = projectRuleMutationDeniedMessage(projectId);
      }
      actions.append(refresh, create);
      header.append(title, actions);
      panel.appendChild(header);
      if (state.loading && !state.loaded) {
        panel.appendChild(ctx.emptyProjectPanel("Loading auto-promote rules..."));
      } else if (state.error) {
        panel.appendChild(ctx.emptyProjectPanel(state.error));
      } else if (!state.rules.length) {
        panel.appendChild(ctx.emptyProjectPanel("No auto-promote rules yet."));
      } else {
        const list = document.createElement("div");
        list.className = "project-auto-promote-list";
        state.rules.forEach((rule) => {
          const ruleId = String(rule.id || "");
          const accessory = document.createElement("div");
          accessory.className = "project-auto-promote-row-actions";
          const preview = ctx.makeProjectButton("Preview", "preview-stored-project-auto-promote-rule", projectId);
          preview.dataset.ruleId = ruleId;
          const edit = ctx.makeProjectButton("Edit", "edit-project-auto-promote-rule", projectId);
          edit.dataset.ruleId = ruleId;
          const apply = ctx.makeProjectButton("Apply now", "apply-project-auto-promote-rule", projectId, "primary");
          apply.dataset.ruleId = ruleId;
          const del = ctx.makeProjectButton("Delete", "delete-project-auto-promote-rule", projectId, "destructive");
          del.dataset.ruleId = ruleId;
          const busy = state.busyRuleId === ruleId;
          if (!canMutateProjectRules(projectId)) {
            [edit, apply, del].forEach((btn) => {
              btn.disabled = true;
              btn.title = projectRuleMutationDeniedMessage(projectId);
            });
          }
          if (rule.enabled === false) {
            preview.disabled = true;
            preview.title = "Disabled rules cannot preview or apply.";
            apply.disabled = true;
            apply.title = "Disabled rules cannot preview or apply.";
          }
          [preview, edit, apply, del].forEach((btn) => {
            btn.disabled = btn.disabled || busy;
          });
          accessory.append(preview, edit, apply, del);
          list.appendChild(ctx.projectItemRow({
            title: String(rule.name || "Untitled rule"),
            meta: rulePatternSummary(rule),
            detail: ruleDetail(rule),
            chips: [
              { label: rule.enabled === false ? "disabled" : "enabled", kind: rule.enabled === false ? "label" : "success" },
              { label: rule.apply_on_run ? "auto-run" : "manual", kind: "label" }
            ],
            accessory,
            forceArticle: true
          }));
        });
        panel.appendChild(list);
      }
      const editor = renderRuleEditor(projectId, state);
      if (editor) panel.appendChild(editor);
      return panel;
    }
    function renderPagination(projectId, total, position = "bottom") {
      const state = page(projectId);
      const offset = Number(state.offset || 0);
      const limit = Math.max(1, Number(state.limit || pageLimit));
      const loading = !!state.loading;
      if (total <= limit && offset === 0) return null;
      const wrap = document.createElement("div");
      wrap.className = "project-workspace-pagination project-entity-pagination";
      wrap.dataset.projectEntitiesPagerPosition = position;
      const start = total ? offset + 1 : 0;
      const end = Math.min(total, offset + limit);
      const summary = document.createElement("div");
      summary.className = "project-workspace-pagination-summary";
      summary.textContent = `${start.toLocaleString()}-${end.toLocaleString()} of ${total.toLocaleString()} entities`;
      const controls = document.createElement("div");
      controls.className = "project-workspace-pagination-controls";
      const prev = ctx.makeProjectButton("Previous", "noop", projectId);
      prev.dataset.projectEntitiesPage = "prev";
      prev.dataset.projectEntitiesPagerPosition = position;
      prev.disabled = loading || offset <= 0;
      const status = document.createElement("span");
      status.className = "project-workspace-pagination-status";
      status.textContent = loading ? "Loading..." : `Page ${Math.floor(offset / limit) + 1}`;
      const next = ctx.makeProjectButton("Next", "noop", projectId);
      next.dataset.projectEntitiesPage = "next";
      next.dataset.projectEntitiesPagerPosition = position;
      next.disabled = loading || offset + limit >= total;
      controls.append(prev, status, next);
      wrap.append(summary, controls);
      return wrap;
    }
    function openInAtlas(projectId, summary, entity) {
      const openAtlas = ctx.openAtlas || typeof exportedOpenAtlas !== "undefined" && exportedOpenAtlas || null;
      if (typeof openAtlas !== "function" || !entity) return;
      const project = summary && summary.project && typeof summary.project === "object" ? summary.project : null;
      const tab = tabs().find((item) => item.type === String(entity.type || ""));
      ctx.closeProjectWorkspace?.({ refocus: false });
      void openAtlas({
        source: "project-workspace",
        projectId,
        projectName: project ? ctx.projectDisplayName(project) : "",
        tab: tab ? tab.id : String(entity.type || ""),
        entityValue: String(entity.canonical_value || entity.value || ""),
        forceView: "detail"
      });
    }
    function closePicker() {
      document.getElementById("project-entity-picker-overlay")?.remove();
      setPickerState(null);
    }
    function pickerLinkedIds(projectId) {
      const summary = ctx.getSummary?.(String(projectId || ""));
      return new Set(items(summary).map((entity) => String(entity && entity.id || "")).filter(Boolean));
    }
    async function loadPickerRows() {
      const state = pickerState();
      if (!state) return;
      state.loading = true;
      renderPicker();
      const params = new URLSearchParams({ limit: "100", orphan_filter: "all" });
      if (state.type) params.set("type", state.type);
      if (state.query) params.set("q", state.query);
      try {
        const resp = await ctx.apiFetch(`/atlas/entities?${params.toString()}`, { cache: "no-store" });
        if (!resp.ok) throw await ctx.projectResponseError(resp, "Could not load Atlas entities.");
        const data = await resp.json();
        const linked = pickerLinkedIds(state.projectId);
        state.rows = (Array.isArray(data.entities) ? data.entities : []).filter((entity) => !linked.has(String(entity && entity.id || "")));
      } catch (err) {
        state.rows = [];
        ctx.setProjectWorkspaceMessage(err && err.message ? err.message : "Could not load Atlas entities.", { error: true });
        if (typeof logClientError === "function") logClientError("failed to load project entity picker", err);
      } finally {
        state.loading = false;
        renderPicker();
      }
    }
    function openPicker(projectId) {
      const currentTabs = tabs();
      const active = currentTabs.find((tab) => tab.id === activeTab()) || currentTabs[0] || { type: "" };
      setPickerState({
        projectId: String(projectId || ""),
        query: "",
        type: active.type || "",
        rows: [],
        selected: /* @__PURE__ */ new Set(),
        loading: false
      });
      renderPicker();
      loadPickerRows().catch(() => {
      });
    }
    function renderPicker() {
      const state = pickerState();
      if (!state) return;
      let overlay = document.getElementById("project-entity-picker-overlay");
      if (!overlay) {
        overlay = document.createElement("div");
        overlay.id = "project-entity-picker-overlay";
        overlay.className = "project-entity-picker-overlay";
        document.body.appendChild(overlay);
      }
      overlay.replaceChildren();
      const modal = document.createElement("div");
      modal.className = "project-entity-picker-modal";
      modal.setAttribute("role", "dialog");
      modal.setAttribute("aria-modal", "true");
      modal.setAttribute("aria-label", "Add Atlas entities to project");
      const header = document.createElement("div");
      header.className = "project-entity-picker-header";
      const title = document.createElement("h3");
      title.textContent = "Add Atlas entities";
      const close = document.createElement("button");
      close.type = "button";
      close.className = "btn btn-ghost btn-icon";
      close.dataset.projectEntityPickerClose = "1";
      close.setAttribute("aria-label", "Close");
      close.textContent = "×";
      header.append(title, close);
      const filters = document.createElement("div");
      filters.className = "project-entity-picker-filters";
      const search = document.createElement("input");
      search.type = "search";
      search.className = "form-control";
      search.placeholder = "Search Atlas entities";
      search.value = state.query;
      search.dataset.projectEntityPickerSearch = "1";
      const type = document.createElement("select");
      type.className = "form-select";
      type.dataset.projectEntityPickerType = "1";
      const all = document.createElement("option");
      all.value = "";
      all.textContent = "All entity types";
      type.appendChild(all);
      tabs().forEach((tab) => {
        const option = document.createElement("option");
        option.value = tab.type;
        option.textContent = tab.label;
        option.selected = tab.type === state.type;
        type.appendChild(option);
      });
      filters.append(search, type);
      const body = document.createElement("div");
      body.className = "project-entity-picker-body";
      if (state.loading) {
        body.appendChild(ctx.emptyProjectPanel("Loading Atlas entities..."));
      } else if (!state.rows.length) {
        body.appendChild(ctx.emptyProjectPanel("No unlinked Atlas entities match this search."));
      } else {
        state.rows.forEach((entity) => {
          const entityId = String(entity.id || "");
          const value = String(entity.canonical_value || entity.value || "");
          const label = document.createElement("label");
          label.className = "project-entity-picker-row panel-row";
          const checkbox = document.createElement("input");
          checkbox.type = "checkbox";
          checkbox.dataset.projectEntityPickerSelect = entityId;
          checkbox.checked = state.selected.has(entityId);
          const textWrap = document.createElement("span");
          textWrap.className = "project-entity-picker-row-text";
          const name = document.createElement("strong");
          name.textContent = value || entityId;
          const meta = document.createElement("span");
          meta.textContent = typeLabel(entity.type);
          textWrap.append(name, meta);
          label.append(checkbox, textWrap);
          body.appendChild(label);
        });
      }
      const footer = document.createElement("div");
      footer.className = "project-entity-picker-footer";
      const count = document.createElement("span");
      count.className = "project-entity-picker-count";
      count.textContent = `${state.selected.size} selected`;
      const cancel = ctx.makeProjectButton("Cancel", "entity-picker-cancel", state.projectId);
      const add = ctx.makeProjectButton("Add selected", "entity-picker-add", state.projectId, "primary");
      add.disabled = state.selected.size === 0;
      footer.append(count, cancel, add);
      modal.append(header, filters, body, footer);
      overlay.appendChild(modal);
      if (document.activeElement === document.body || !modal.contains(document.activeElement)) search.focus();
    }
    function renderEntities(container, projectId, summary) {
      const state = page(projectId);
      const filterKey = entityFilterParams(projectId, state).toString();
      const visibleEntities = pagedItemsForActiveTab(projectId, summary);
      const totalEntities = Number(summary?.counts?.entities || 0);
      const activeTotal = state.loaded ? Number(state.total || 0) : Number(counts(summary)[activeType()] || 0);
      const currentSelected = selectedIds();
      currentSelected.forEach((entityId) => {
        if (!visibleEntities.some((entity) => String(entity && entity.id || "") === entityId)) {
          currentSelected.delete(entityId);
        }
      });
      container.appendChild(renderTypeTabs(projectId, summary));
      container.appendChild(renderToolbar(projectId, visibleEntities));
      const rulesPanel = renderRulesPanel(projectId);
      if (rulesPanel) container.appendChild(rulesPanel);
      if (!totalEntities) {
        container.appendChild(ctx.emptyProjectPanel("No Atlas entities are linked to this project yet."));
        return;
      }
      if ((!state.loaded || state.filterKey !== filterKey) && !state.loading) {
        load(projectId, { offset: state.filterKey === filterKey ? state.offset : 0 }).catch(() => {
        });
      }
      if (state.loading && !visibleEntities.length) {
        container.appendChild(ctx.emptyProjectPanel("Loading project entities..."));
        return;
      }
      if (state.error && !visibleEntities.length) {
        container.appendChild(ctx.emptyProjectPanel(state.error));
        return;
      }
      if (!activeTotal) {
        const activeType2 = tabs().find((tab) => tab.id === activeTab())?.type || "";
        container.appendChild(ctx.emptyProjectPanel(`No ${typeLabel(activeType2).toLowerCase()} linked yet.`));
        return;
      }
      const topPager = renderPagination(projectId, activeTotal, "top");
      if (topPager) container.appendChild(topPager);
      visibleEntities.forEach((entity) => {
        const entityId = String(entity.id || "");
        const value = String(entity.canonical_value || entity.value || "");
        const hitCount = Number(entity.occurrence_count || entity.seen_count || 0);
        const metaParts = [
          typeLabel(entity.type),
          `${hitCount.toLocaleString()} hit${hitCount === 1 ? "" : "s"}`,
          entity.last_seen ? `last seen ${ctx.formatDate(entity.last_seen)}` : ""
        ].filter(Boolean);
        const detailParts = [
          entity.source_run_id ? `source run ${ctx.shortProjectRunId(entity.source_run_id)}` : "",
          intelSummary(entity)
        ].filter(Boolean);
        const checkbox = selectMode() ? document.createElement("input") : null;
        if (checkbox) {
          checkbox.type = "checkbox";
          checkbox.className = "project-entity-select-checkbox";
          checkbox.checked = currentSelected.has(entityId);
          checkbox.dataset.projectEntitySelect = entityId;
          checkbox.dataset.projectId = projectId;
          checkbox.setAttribute("aria-label", `Select ${value || entityId}`);
        }
        const renderProjectEntityRow = typeof entityRowApi.renderProjectEntityRow === "function" ? entityRowApi.renderProjectEntityRow : _fallbackProjectEntityRow;
        const row = renderProjectEntityRow({
          entity,
          projectId,
          title: value || entityId,
          meta: metaParts.join(" · "),
          detail: detailParts.join(" · "),
          chips: chips(entity),
          accessory: rowAccessory(projectId, entity),
          checkbox,
          selected: currentSelected.has(entityId),
          chipClass: ctx.entityMetadataChipClass,
          bindPressable: ctx.bindProjectRuntimePressable,
          action: {
            action: selectMode() ? "toggle-project-entity-row" : "open-project-entity",
            dataset: { projectId, entityId, entityValue: value, entityType: String(entity.type || "") }
          }
        });
        container.appendChild(row);
      });
      const bottomPager = renderPagination(projectId, activeTotal, "bottom");
      if (bottomPager) container.appendChild(bottomPager);
    }
    function renderMobileEntitiesTab(projectId, summary) {
      const fragment = document.createDocumentFragment();
      const toolbar = document.createElement("div");
      toolbar.className = "project-mobile-tab-toolbar";
      const rules = ctx.makeProjectButton("Rules", "toggle-project-auto-promote-rules", projectId);
      rules.classList.add("project-auto-promote-rules-toggle");
      rules.setAttribute("aria-expanded", ruleState(projectId).open ? "true" : "false");
      rules.setAttribute("aria-controls", rulesPanelId(projectId));
      toolbar.append(
        ctx.makeProjectButton("Add entity", "open-entity-picker", projectId, "primary"),
        rules,
        ctx.makeProjectButton("Export CSV", "export-project-entities-csv", projectId)
      );
      fragment.appendChild(toolbar);
      fragment.appendChild(renderTypeTabs(projectId, summary));
      const rulesPanel = renderRulesPanel(projectId);
      if (rulesPanel) fragment.appendChild(rulesPanel);
      const state = page(projectId);
      const visibleEntities = pagedItemsForActiveTab(projectId, summary);
      const totalEntities = Number(summary?.counts?.entities || 0);
      const activeTotal = state.loaded ? Number(state.total || 0) : Number(counts(summary)[activeType()] || 0);
      if (!totalEntities) {
        fragment.appendChild(ctx.projectMobileEmptyPanel("No Atlas entities are linked to this project yet.", [
          ctx.makeProjectButton("Add entity", "open-entity-picker", projectId, "primary")
        ]));
        return fragment;
      }
      const filterKey = entityFilterParams(projectId, state).toString();
      if ((!state.loaded || state.filterKey !== filterKey) && !state.loading) {
        load(projectId, { offset: state.filterKey === filterKey ? state.offset : 0 }).catch(() => {
        });
      }
      if (state.loading && !visibleEntities.length) {
        fragment.appendChild(ctx.emptyProjectPanel("Loading project entities..."));
        return fragment;
      }
      if (state.error && !visibleEntities.length) {
        fragment.appendChild(ctx.emptyProjectPanel(state.error));
        return fragment;
      }
      if (!activeTotal) {
        fragment.appendChild(ctx.emptyProjectPanel("No entities match this type."));
        return fragment;
      }
      const topPager = renderPagination(projectId, activeTotal, "top");
      if (topPager) fragment.appendChild(topPager);
      const list = document.createElement("div");
      list.className = "project-mobile-content-list";
      visibleEntities.forEach((entity) => {
        const entityId = String(entity.id || "");
        const value = String(entity.canonical_value || entity.value || "");
        const hitCount = Number(entity.occurrence_count || entity.seen_count || 0);
        const actions = [
          { label: "Open in Atlas", action: "open-project-entity", dataset: { entityId, entityValue: value, entityType: entity.type } },
          { label: "Unlink", action: "unlink-project-entity", tone: "danger", dataset: { entityId, entityValue: value } }
        ];
        list.appendChild(ctx.projectMobileContentRow({
          title: value || entityId,
          meta: typeLabel(entity.type),
          detail: [
            `${hitCount.toLocaleString()} hit${hitCount === 1 ? "" : "s"}`,
            intelSummary(entity)
          ].filter(Boolean),
          chips: chips(entity),
          action: {
            action: "open-project-entity",
            dataset: { projectId, entityId, entityValue: value, entityType: String(entity.type || "") }
          },
          accessory: ctx.projectMobileActionMenu(projectId, `Entity actions for ${value || entityId}`, actions)
        }));
      });
      fragment.appendChild(list);
      const bottomPager = renderPagination(projectId, activeTotal, "bottom");
      if (bottomPager) fragment.appendChild(bottomPager);
      return fragment;
    }
    function handlePickerInput(event) {
      const search = event.target.closest?.("[data-project-entity-picker-search]");
      const state = pickerState();
      if (!search || !state) return false;
      state.query = String(search.value || "");
      window.clearTimeout(state.searchTimer);
      state.searchTimer = window.setTimeout(() => {
        loadPickerRows().catch(() => {
        });
      }, 200);
      return true;
    }
    function handlePickerChange(event) {
      const state = pickerState();
      const pickerType = event.target.closest?.("[data-project-entity-picker-type]");
      if (pickerType && state) {
        state.type = String(pickerType.value || "");
        state.selected.clear();
        loadPickerRows().catch(() => {
        });
        return true;
      }
      const pickerSelect = event.target.closest?.("[data-project-entity-picker-select]");
      if (pickerSelect && state) {
        const entityId = String(pickerSelect.dataset.projectEntityPickerSelect || "");
        if (entityId) {
          if (pickerSelect.checked) state.selected.add(entityId);
          else state.selected.delete(entityId);
        }
        renderPicker();
        return true;
      }
      return false;
    }
    async function handlePickerClick(event) {
      const state = pickerState();
      if (!state) return false;
      const overlay = document.getElementById("project-entity-picker-overlay");
      if (!overlay || !overlay.contains(event.target)) return false;
      const close = event.target.closest?.("[data-project-entity-picker-close]");
      const cancel = event.target.closest?.('[data-project-action="entity-picker-cancel"]');
      if (close || cancel) {
        event.preventDefault();
        closePicker();
        return true;
      }
      const add = event.target.closest?.('[data-project-action="entity-picker-add"]');
      if (add) {
        event.preventDefault();
        const entityIds = [...state.selected];
        if (!entityIds.length) return true;
        try {
          await ctx.projectWorkspaceRequest(`/projects/${encodeURIComponent(state.projectId)}/links`, {
            method: "POST",
            body: JSON.stringify({ entity_type: "atlas_entity", entity_ids: entityIds })
          });
          closePicker();
          ctx.setWorkspaceTab?.("entities");
          await ctx.refreshProjectWorkspace();
          ctx.setProjectWorkspaceMessage(`${entityIds.length} ${entityIds.length === 1 ? "entity" : "entities"} added to project.`);
        } catch (err) {
          ctx.setProjectWorkspaceMessage(err && err.message ? err.message : "Could not add Atlas entities.", { error: true });
        }
        return true;
      }
      return false;
    }
    function updateEditorFromControl(control) {
      const projectId = String(control.dataset.projectId || ctx.getSelectedProjectId?.() || "");
      const state = ruleState(projectId);
      if (!state.editor) return false;
      const field = String(control.dataset.projectAutoPromoteField || "");
      if (!field) return false;
      if (control.type === "checkbox") state.editor[field] = !!control.checked;
      else state.editor[field] = String(control.value || "");
      if (field === "target_entity_kind") normalizeRuleEditorMatchMode(state.editor);
      if (previewRelevantField(field)) {
        state.preview = null;
        state.previewKey = "";
      }
      return true;
    }
    function handleAutoPromoteInput(event) {
      const control = event.target.closest?.("[data-project-auto-promote-field]");
      if (!control) return false;
      updateEditorFromControl(control);
      return true;
    }
    function handleAutoPromoteChange(event) {
      const control = event.target.closest?.("[data-project-auto-promote-field]");
      if (!control) return false;
      updateEditorFromControl(control);
      const tagName = String(control.tagName || "").toUpperCase();
      const type = String(control.type || "").toLowerCase();
      if (tagName === "INPUT" && type !== "checkbox" && type !== "radio") return true;
      ctx.renderProjectExplorer?.();
      return true;
    }
    function ruleById(projectId, ruleId) {
      return ruleState(projectId).rules.find((rule) => String(rule && rule.id || "") === String(ruleId || "")) || null;
    }
    async function handleAutoPromoteClick(event) {
      const btn = event.target.closest?.("[data-project-action]");
      if (!btn) return false;
      const action = String(btn.dataset.projectAction || "");
      if (!action.includes("project-auto-promote")) return false;
      event.preventDefault();
      event.stopPropagation();
      const projectId = String(btn.dataset.projectId || ctx.getSelectedProjectId?.() || "");
      const state = ruleState(projectId);
      const ruleId = String(btn.dataset.ruleId || "");
      const rule = ruleById(projectId, ruleId);
      if (action === "toggle-project-auto-promote-rules") {
        setRulesOpen(projectId, !state.open);
        ctx.renderProjectExplorer?.();
        return true;
      }
      if (action === "refresh-project-auto-promote-rules") {
        await loadRules(projectId, { force: true });
        return true;
      }
      if (action === "new-project-auto-promote-rule") {
        if (!canMutateProjectRules(projectId)) {
          denyProjectMutation(projectId);
          return true;
        }
        setRulesOpen(projectId, true);
        setEditor(projectId, defaultRuleEditor(projectId));
        ctx.renderProjectExplorer?.();
        return true;
      }
      if (action === "edit-project-auto-promote-rule") {
        if (!canMutateProjectRules(projectId)) {
          denyProjectMutation(projectId);
          return true;
        }
        if (!rule) return true;
        setEditor(projectId, defaultRuleEditor(projectId, rule));
        ctx.renderProjectExplorer?.();
        return true;
      }
      if (action === "cancel-project-auto-promote-rule") {
        setEditor(projectId, null);
        ctx.renderProjectExplorer?.();
        return true;
      }
      if (action === "preview-project-auto-promote-rule") {
        await previewEditorRule(projectId);
        return true;
      }
      if (action === "save-project-auto-promote-rule") {
        await saveEditorRule(projectId);
        return true;
      }
      if (action === "preview-stored-project-auto-promote-rule") {
        if (!rule) return true;
        try {
          const preview = await previewStoredRule(projectId, rule);
          ctx.setProjectWorkspaceMessage?.(`Auto-promote preview: ${previewSummaryText(preview)}.`);
        } catch (err) {
          ctx.setProjectWorkspaceMessage?.(err && err.message ? err.message : "Could not preview auto-promote rule.", {
            error: true
          });
          logAutoPromoteClientError("stored preview", projectId, err, rule.id || "");
        }
        return true;
      }
      if (action === "apply-project-auto-promote-rule") {
        if (rule) await applyStoredRule(projectId, rule);
        return true;
      }
      if (action === "delete-project-auto-promote-rule") {
        if (rule) await deleteStoredRule(projectId, rule);
        return true;
      }
      return false;
    }
    function setActiveTab(tabId) {
      ctx.setActiveTab?.(String(tabId || "ip"));
      resetPages();
    }
    function toggleSelected(entityId, checked = null) {
      const normalized = String(entityId || "");
      if (!normalized) return;
      const currentSelected = selectedIds();
      if (checked === true) currentSelected.add(normalized);
      else if (checked === false) currentSelected.delete(normalized);
      else if (currentSelected.has(normalized)) currentSelected.delete(normalized);
      else currentSelected.add(normalized);
    }
    function selectAllForActiveTab(summary) {
      pagedItemsForActiveTab(ctx.getSelectedProjectId?.() || "", summary).forEach((entity) => {
        if (entity && entity.id) selectedIds().add(String(entity.id));
      });
    }
    function clearSelection() {
      selectedIds().clear();
    }
    function setSelectMode(nextMode) {
      ctx.setSelectMode?.(!!nextMode);
    }
    function exportEntities(projectId, format) {
      const normalizedFormat = String(format || "") === "jsonl" ? "jsonl" : "csv";
      const params = new URLSearchParams({ format: normalizedFormat, project_id: projectId, orphan_filter: "all" });
      const tab = tabs().find((item) => item.id === activeTab());
      if (tab && tab.type) params.set("type", tab.type);
      return ctx.projectWorkspaceRequest(`/atlas/entities/export?${params.toString()}`, { cache: "no-store" }).then((resp) => resp.blob()).then((blob) => {
        const filename = `darklab-project-entities-${projectId}.${normalizedFormat}`;
        ctx.downloadBlobAsAttachment(blob, filename, `Project ${normalizedFormat.toUpperCase()} export started.`);
      });
    }
    return {
      items,
      tabs,
      typeLabel,
      intelSummary,
      counts,
      itemsForActiveTab,
      pagedItemsForActiveTab,
      byId,
      load,
      invalidate,
      ensureFilteredCounts,
      tabCountText,
      chips,
      renderTypeTabs,
      renderEntities,
      renderMobileEntitiesTab,
      openInAtlas,
      openAutoPromoteRuleEditor,
      openAutoPromoteRuleFromAtlas,
      closePicker,
      loadPickerRows,
      openPicker,
      renderPicker,
      handlePickerInput,
      handlePickerChange,
      handlePickerClick,
      handleAutoPromoteInput,
      handleAutoPromoteChange,
      handleAutoPromoteClick,
      setActiveTab,
      page,
      setPageOffset,
      toggleSelected,
      selectAllForActiveTab,
      clearSelection,
      setSelectMode,
      exportEntities
    };
  }
  const DarklabProjectEntities = {
    createProjectEntitiesController
  };
  exportedDarklabProjectEntities = DarklabProjectEntities;
})(globalThis);
export {
  exportedDarklabProjectEntities as DarklabProjectEntities
};
