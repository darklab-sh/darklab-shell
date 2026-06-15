import {
  DarklabStatusMonitorCore
} from "./static-chunk-6pbz2pva.3fa98e8a1a1c.js";
import {
  DarklabStatusMonitorData
} from "./static-chunk-upf2irez.a74d75f427ca.js";
import {
  DarklabStatusMonitorResources
} from "./static-chunk-kmoqzqyh.66ddc1897f15.js";
import {
  restoreHistoryRun
} from "./static-chunk-3jpzlov4.47e7ebc68e55.js";
import {
  activateTab,
  applyConstellationFullDayPreference,
  attachActiveRunFromMonitor,
  getConstellationFullDayPreference,
  killActiveRunFromMonitor,
  pauseBackgroundRunStreamsForStatusMonitor,
  resumeBackgroundRunStreamsAfterStatusMonitor
} from "./static-chunk-n2vpqjbs.2f664fbfac6b.js";
import {
  showToast
} from "./static-chunk-poi5czx6.3f5c94749765.js";
import "./static-chunk-lxs2zdd2.87dc9e4c1317.js";
import {
  bindDismissible,
  bindFocusTrap,
  bindMobileSheet,
  bindPressable
} from "./static-chunk-fik64llj.1291b1f4f79b.js";
import "./static-chunk-yu6ty7m2.96c3ee208a44.js";
import {
  getTabs,
  openHistoryWithFilters,
  syncModalOverlayState
} from "./static-chunk-sgyzdmxn.7d1842f12a94.js";
import "./static-chunk-tym5o2af.a748583ae389.js";
import {
  apiFetch,
  hasRuntimeHandler,
  setRuntimeHandlers
} from "./static-chunk-i34eiczq.4bb950c346dc.js";

// app/static/js/status_monitor.js
var exportedOpenStatusMonitor = null;
var exportedCloseStatusMonitor = null;
var exportedIsStatusMonitorOpen = null;
var exportedRefreshStatusMonitor = null;
var exportedConstellationTestHelpers = null;
(function(global) {
  function _statusMonitorGlobalFunction(name) {
    const fn = global && global[name];
    return typeof fn === "function" ? fn : null;
  }
  function _statusMonitorGlobalValue(name) {
    return global ? global[name] : void 0;
  }
  const _statusMonitorCore = typeof DarklabStatusMonitorCore !== "undefined" && DarklabStatusMonitorCore || _statusMonitorGlobalValue("DarklabStatusMonitorCore");
  if (!_statusMonitorCore) throw new Error("DarklabStatusMonitorCore is unavailable");
  const getTabsFn = typeof getTabs !== "undefined" && getTabs || _statusMonitorGlobalFunction("getTabs");
  const showToastFn = typeof showToast !== "undefined" && showToast || _statusMonitorGlobalFunction("showToast");
  const openHistoryWithFiltersFn = typeof openHistoryWithFilters !== "undefined" && openHistoryWithFilters || _statusMonitorGlobalFunction("openHistoryWithFilters");
  const restoreHistoryRunFn = typeof restoreHistoryRun !== "undefined" && restoreHistoryRun || _statusMonitorGlobalFunction("restoreHistoryRun");
  const activateTabFn = typeof activateTab !== "undefined" && activateTab || _statusMonitorGlobalFunction("activateTab");
  const attachActiveRunFromMonitorFn = typeof attachActiveRunFromMonitor !== "undefined" && attachActiveRunFromMonitor || _statusMonitorGlobalFunction("attachActiveRunFromMonitor");
  const killActiveRunFromMonitorFn = typeof killActiveRunFromMonitor !== "undefined" && killActiveRunFromMonitor || _statusMonitorGlobalFunction("killActiveRunFromMonitor");
  const bindMobileSheetFn = typeof bindMobileSheet !== "undefined" && bindMobileSheet || _statusMonitorGlobalFunction("bindMobileSheet");
  const bindDismissibleFn = typeof bindDismissible !== "undefined" && bindDismissible || _statusMonitorGlobalFunction("bindDismissible");
  const bindFocusTrapFn = typeof bindFocusTrap !== "undefined" && bindFocusTrap || _statusMonitorGlobalFunction("bindFocusTrap");
  const bindPressableFn = typeof bindPressable !== "undefined" && bindPressable || _statusMonitorGlobalFunction("bindPressable");
  function _attachInteractivePtyCommand() {
    return _statusMonitorGlobalFunction("attachInteractivePtyCommand");
  }
  let monitorEl = null;
  let scrimEl = null;
  let listEl = null;
  let summaryEl = null;
  let pollTimer = null;
  let tickTimer = null;
  let closedPollTimer = null;
  let warmupTimer = null;
  let openFollowupTimer = null;
  let isOpen = false;
  let cachedRuns = [];
  let cachedStatus = null;
  let cachedWorkspace = null;
  let cachedStats = null;
  let cachedInsights = null;
  let latestPulseData = null;
  let pulseAnimationFrame = null;
  let pulseBucketedAverageCpu = null;
  let pulseBucketedActiveCount = null;
  let lastPulseRenderAt = null;
  let suppressPulseLoadUntilFresh = false;
  const pulseRecentCpuSamples = [];
  const POLL_MS = 3e3;
  const CLOSED_POLL_MS = 8e3;
  const CPU_SAMPLE_WARMUP_MS = 900;
  let statusMonitorResources = null;
  let statusMonitorData = null;
  const pulseStateByStrip = /* @__PURE__ */ new WeakMap();
  const pulseNodeCacheByStrip = /* @__PURE__ */ new WeakMap();
  const activeRunByRow = /* @__PURE__ */ new WeakMap();
  const categoryToneCache = /* @__PURE__ */ new Map();
  const constellationPopoverTimerByPanel = /* @__PURE__ */ new WeakMap();
  const SVG_NS = "http://www.w3.org/2000/svg";
  const PULSE_BASELINE_Y = 40;
  const PULSE_VIEW_WIDTH = 720;
  const PULSE_PATH_MARGIN = 240;
  const PULSE_SCROLL_PX_PER_MS = 0.072;
  const PULSE_FRAME_MS = 1e3 / 45;
  const PULSE_FRESH_LIVE_WINDOW = 104;
  const PULSE_CPU_BUCKET_HYSTERESIS = 8;
  const PULSE_RECENT_CPU_SAMPLE_LIMIT = 8;
  const CONSTELLATION_POPOVER_MOVE_DELAY_MS = 80;
  const CONSTELLATION_PLOT_LEFT = 38;
  const CONSTELLATION_PLOT_WIDTH = 580;
  const CONSTELLATION_PLOT_RIGHT = CONSTELLATION_PLOT_LEFT + CONSTELLATION_PLOT_WIDTH;
  const CONSTELLATION_Y_BASELINE = 260;
  const CONSTELLATION_Y_RANGE = 205;
  const DAY_MS = 864e5;
  const _normalizedExitCode = _statusMonitorCore.normalizedExitCode;
  const _isGracefulTerminationExitCode = _statusMonitorCore.isGracefulTerminationExitCode;
  const _isFailedExitCode = _statusMonitorCore.isFailedExitCode;
  const _exitCodeLabel = _statusMonitorCore.exitCodeLabel;
  const _formatElapsed = _statusMonitorCore.formatElapsed;
  const _shortRunId = _statusMonitorCore.shortRunId;
  const _formatCpuPercent = _statusMonitorCore.formatCpuPercent;
  const _isTelemetryNumber = _statusMonitorCore.isTelemetryNumber;
  const _formatMemoryBytes = _statusMonitorCore.formatMemoryBytes;
  const _formatDurationSeconds = _statusMonitorCore.formatDurationSeconds;
  const _formatCount = _statusMonitorCore.formatCount;
  const _truncateText = _statusMonitorCore.truncateText;
  const _normalizedHash = _statusMonitorCore.normalizedHash;
  const _parseIsoDateOnly = _statusMonitorCore.parseIsoDateOnly;
  const _formatIsoDateOnly = _statusMonitorCore.formatIsoDateOnly;
  const _isoWeekdayRow = _statusMonitorCore.isoWeekdayRow;
  function _isMobileStatusMonitor() {
    return !!(document.body?.classList?.contains("mobile-terminal-mode") || window.matchMedia && window.matchMedia("(max-width: 600px)").matches);
  }
  function _statusMonitorResources() {
    if (!statusMonitorResources) {
      const resourcesFactory = typeof DarklabStatusMonitorResources !== "undefined" && DarklabStatusMonitorResources || _statusMonitorGlobalValue("DarklabStatusMonitorResources");
      if (!resourcesFactory?.create) {
        throw new Error("DarklabStatusMonitorResources is unavailable");
      }
      statusMonitorResources = resourcesFactory.create({
        core: _statusMonitorCore,
        svgEl: _svgEl,
        pathFromPoints: _pathFromPoints
      });
    }
    return statusMonitorResources;
  }
  function _statusMonitorData() {
    if (!statusMonitorData) {
      const dataFactory = typeof DarklabStatusMonitorData !== "undefined" && DarklabStatusMonitorData || _statusMonitorGlobalValue("DarklabStatusMonitorData");
      if (!dataFactory?.create) {
        throw new Error("DarklabStatusMonitorData is unavailable");
      }
      const fetchImpl = (typeof hasRuntimeHandler === "function" && hasRuntimeHandler("apiFetch") && typeof apiFetch === "function" ? apiFetch : null) || _statusMonitorGlobalFunction("apiFetch");
      statusMonitorData = dataFactory.create({ apiFetch: fetchImpl });
    }
    return statusMonitorData;
  }
  function _runResourceUsage(run) {
    return _statusMonitorResources().runResourceUsage(run);
  }
  function _recordResourceTrend(run, usage) {
    return _statusMonitorResources().recordResourceTrend(run, usage);
  }
  function _trendPath(samples, key, width = 160, height = 34) {
    return _statusMonitorResources().trendPath(samples, key, width, height);
  }
  function _runMetaChip(text, className = "") {
    const chip = document.createElement("span");
    chip.className = `status-monitor-meta-chip ${className}`.trim();
    chip.textContent = text;
    return chip;
  }
  function _runSparklinePanel(run, usage) {
    return _statusMonitorResources().runSparklinePanel(run, usage);
  }
  function _runsNeedCpuFollowup(runs) {
    return _statusMonitorResources().runsNeedCpuFollowup(runs);
  }
  function _currentStatusUptimeSeconds(status = cachedStatus) {
    if (!status || !_isTelemetryNumber(status.uptime)) return null;
    const base = Number(status.uptime);
    const receivedAt = Number(status.uptime_received_at_ms || 0);
    if (!Number.isFinite(receivedAt) || receivedAt <= 0) return base;
    return base + Math.max(0, (Date.now() - receivedAt) / 1e3);
  }
  function _statusMonitorUptimeText(status = cachedStatus) {
    const uptime = _currentStatusUptimeSeconds(status);
    return uptime === null ? "n/a" : _formatDurationSeconds(uptime);
  }
  function _insightWindowInfo(key, fallbackDays = 30) {
    const insights = cachedInsights || {};
    const windows = insights && typeof insights.windows === "object" ? insights.windows : null;
    const info = windows && typeof windows[key] === "object" ? windows[key] : null;
    const days = Number(info?.days || fallbackDays);
    const label = String(info?.label || "").trim();
    return {
      days,
      label: label || (days > 0 ? `last ${days} days` : "")
    };
  }
  function _insightWindowLabel(key, fallbackDays = 30) {
    return _insightWindowInfo(key, fallbackDays).label;
  }
  function _categoryTone(category) {
    const normalized = String(category || "").trim().toLowerCase();
    const cached = categoryToneCache.get(normalized);
    if (cached) return cached;
    let tone = { hue: 0, saturation: 0 };
    if (normalized.includes("vulner")) tone = { hue: 28, saturation: 100 };
    else if (normalized.includes("tls") || normalized.includes("cert")) tone = { hue: 184, saturation: 100 };
    else if (normalized.includes("recon")) tone = { hue: 207, saturation: 100 };
    else if (normalized.includes("diagnostic")) tone = { hue: 92, saturation: 100 };
    else if (normalized.includes("utility")) tone = { hue: 258, saturation: 88 };
    categoryToneCache.set(normalized, tone);
    return tone;
  }
  function _constellationToneStyle(tone, extraVars = {}) {
    const style = [];
    const hue = Number(tone?.hue);
    const saturation = Number(tone?.saturation);
    if (Number.isFinite(hue)) style.push(`--star-hue:${hue}`);
    if (Number.isFinite(saturation)) style.push(`--star-saturation:${saturation}%`);
    Object.entries(extraVars).forEach(([key, value]) => {
      if (!key || value === void 0 || value === null) return;
      style.push(`${key}:${value}`);
    });
    return style.join(";");
  }
  function _constellationKindClass(kind, prefix) {
    const normalized = String(kind || "").trim().toLowerCase();
    if (normalized === "error") return `${prefix}-kind-error`;
    if (normalized === "warn") return `${prefix}-kind-warn`;
    return "";
  }
  function _categoryLegendLabel(category) {
    const normalized = String(category || "").trim().toLowerCase();
    if (normalized.includes("vulner")) return "Vuln";
    if (normalized.includes("tls") || normalized.includes("cert")) return "TLS";
    if (normalized.includes("recon")) return "Recon";
    if (normalized.includes("diagnostic")) return "Diag";
    if (normalized.includes("utility")) return "Util";
    return _truncateText(category || "Other", 12);
  }
  function _categoryLegend(items) {
    const counts = /* @__PURE__ */ new Map();
    (Array.isArray(items) ? items : []).forEach((item) => {
      const category = String(item?.category || "").trim() || "Other";
      const key = category.toLowerCase();
      const existing = counts.get(key) || { category, count: 0 };
      existing.count += Math.max(1, Number(item?.count || 1));
      counts.set(key, existing);
    });
    const entries = [...counts.values()].sort((left, right) => right.count - left.count || left.category.localeCompare(right.category)).slice(0, 4);
    if (!entries.length) return null;
    const legend = document.createElement("div");
    legend.className = "status-monitor-category-legend";
    entries.forEach(({ category }) => {
      const tone = _categoryTone(category);
      const item = document.createElement("span");
      item.className = "status-monitor-category-legend-item";
      item.title = category;
      item.style.setProperty("--legend-hue", String(tone.hue));
      item.style.setProperty("--legend-saturation", `${tone.saturation}%`);
      const dot = document.createElement("span");
      dot.className = "status-monitor-category-legend-dot";
      dot.setAttribute("aria-hidden", "true");
      const label = document.createElement("span");
      label.className = "status-monitor-category-legend-label";
      label.textContent = _categoryLegendLabel(category);
      item.append(dot, label);
      legend.appendChild(item);
    });
    return legend;
  }
  function _buildConstellationLegendKey({ modifier, ariaLabel, label }) {
    const item = document.createElement("span");
    item.className = `status-monitor-category-legend-item status-monitor-legend-key status-monitor-legend-key-${modifier}`;
    item.setAttribute("aria-label", ariaLabel);
    const glyph = document.createElement("span");
    glyph.className = `status-monitor-legend-key-glyph status-monitor-legend-key-glyph-${modifier}`;
    glyph.setAttribute("aria-hidden", "true");
    if (modifier === "size") {
      const small = _svgEl("svg", {
        class: "status-monitor-legend-star-svg status-monitor-legend-star-svg-small",
        viewBox: "0 0 8 8",
        "aria-hidden": "true"
      });
      small.appendChild(_svgEl("circle", {
        class: "status-monitor-star",
        cx: 4,
        cy: 4,
        r: 1.8
      }));
      const large = _svgEl("svg", {
        class: "status-monitor-legend-star-svg status-monitor-legend-star-svg-large",
        viewBox: "0 0 18 18",
        "aria-hidden": "true"
      });
      large.appendChild(_svgEl("circle", {
        class: "status-monitor-star",
        cx: 9,
        cy: 9,
        r: 7
      }));
      glyph.append(small, large);
    }
    const text = document.createElement("span");
    text.className = "status-monitor-category-legend-label";
    text.textContent = label;
    item.append(glyph, text);
    return item;
  }
  const CONSTELLATION_FULL_DAY_WINDOW = Object.freeze({ startMin: 0, endMin: 1440 });
  function _constellationStarMinutes(star) {
    const started = Date.parse(String(star?.started || ""));
    if (!Number.isFinite(started)) return null;
    const date = new Date(started);
    return date.getHours() * 60 + date.getMinutes();
  }
  function _constellationHourDensity(stars) {
    const bins = new Array(24).fill(0);
    if (!Array.isArray(stars)) return bins;
    for (const star of stars) {
      const minutes = _constellationStarMinutes(star);
      if (minutes === null) continue;
      const hour = Math.min(23, Math.max(0, Math.floor(minutes / 60)));
      bins[hour] += 1;
    }
    const peak = bins.reduce((max, value) => value > max ? value : max, 0);
    if (peak <= 0) return bins.map(() => 0);
    return bins.map((value) => value / peak);
  }
  function _constellationPercentileMinute(sortedMinutes, fraction) {
    if (!sortedMinutes.length) return 0;
    if (sortedMinutes.length === 1) return sortedMinutes[0];
    const clamped = Math.min(1, Math.max(0, fraction));
    const position = clamped * (sortedMinutes.length - 1);
    const lower = Math.floor(position);
    const upper = Math.ceil(position);
    if (lower === upper) return sortedMinutes[lower];
    const weight = position - lower;
    return sortedMinutes[lower] * (1 - weight) + sortedMinutes[upper] * weight;
  }
  function _constellationActiveWindow(stars, { paddingMinutes = 60 } = {}) {
    const minutes = [];
    if (Array.isArray(stars)) {
      for (const star of stars) {
        const value = _constellationStarMinutes(star);
        if (value !== null) minutes.push(value);
      }
    }
    if (minutes.length < 6) return { startMin: 0, endMin: 1440 };
    minutes.sort((left, right) => left - right);
    const lower = _constellationPercentileMinute(minutes, 0.05);
    const upper = _constellationPercentileMinute(minutes, 0.95);
    const pad = Math.max(0, Number(paddingMinutes) || 0);
    const startMin = Math.max(0, Math.floor(lower - pad));
    const endMin = Math.min(1440, Math.ceil(upper + pad));
    if (endMin <= startMin) return { startMin: 0, endMin: 1440 };
    return { startMin, endMin };
  }
  const CONSTELLATION_DEAD_BAND_DENSITY = 0.15;
  const CONSTELLATION_DEAD_BAND_MIN_HOURS = 2;
  const CONSTELLATION_DEAD_BAND_EDGE_PAD_MIN = 30;
  const CONSTELLATION_DEAD_BAND_MIN_STARS = 30;
  function _constellationDeadBands(stars, {
    densityThreshold = CONSTELLATION_DEAD_BAND_DENSITY,
    minBandHours = CONSTELLATION_DEAD_BAND_MIN_HOURS,
    edgePaddingMinutes = CONSTELLATION_DEAD_BAND_EDGE_PAD_MIN,
    minStars = CONSTELLATION_DEAD_BAND_MIN_STARS
  } = {}) {
    if (!Array.isArray(stars) || stars.length < minStars) return [];
    const density = _constellationHourDensity(stars);
    const hourRuns = [];
    let runStart = null;
    for (let h = 0; h < 24; h += 1) {
      const isDead = density[h] <= densityThreshold;
      if (isDead && runStart === null) runStart = h;
      if (!isDead && runStart !== null) {
        if (h - runStart >= minBandHours) hourRuns.push({ startHour: runStart, endHour: h });
        runStart = null;
      }
    }
    if (runStart !== null && 24 - runStart >= minBandHours) {
      hourRuns.push({ startHour: runStart, endHour: 24 });
    }
    return hourRuns.map(({ startHour, endHour }) => ({
      startMin: Math.min(1440, startHour * 60 + edgePaddingMinutes),
      endMin: Math.max(0, endHour * 60 - edgePaddingMinutes)
    })).filter((band) => band.endMin - band.startMin >= 60);
  }
  function _constellationVisibleSegments(window2, deadBands) {
    const safeWindow = {
      startMin: Math.max(0, Number(window2?.startMin) || 0),
      endMin: Math.min(1440, Number(window2?.endMin) || 1440)
    };
    if (safeWindow.endMin <= safeWindow.startMin) {
      return [{ startMin: 0, endMin: 1440 }];
    }
    const bands = (Array.isArray(deadBands) ? deadBands : []).map((band) => ({
      startMin: Math.max(safeWindow.startMin, Number(band?.startMin) || 0),
      endMin: Math.min(safeWindow.endMin, Number(band?.endMin) || 0)
    })).filter((band) => band.endMin > band.startMin).sort((left, right) => left.startMin - right.startMin);
    if (!bands.length) return [{ startMin: safeWindow.startMin, endMin: safeWindow.endMin }];
    const segments = [];
    let cursor = safeWindow.startMin;
    for (const band of bands) {
      if (band.endMin <= cursor) continue;
      if (band.startMin > cursor) segments.push({ startMin: cursor, endMin: band.startMin });
      cursor = Math.max(cursor, band.endMin);
    }
    if (cursor < safeWindow.endMin) segments.push({ startMin: cursor, endMin: safeWindow.endMin });
    return segments.length ? segments : [{ startMin: safeWindow.startMin, endMin: safeWindow.endMin }];
  }
  function _constellationMinuteToX(window2, segments) {
    const rawWindowStart = Number(window2?.startMin);
    const rawWindowEnd = Number(window2?.endMin);
    const windowStart = Number.isFinite(rawWindowStart) ? rawWindowStart : 0;
    const windowEnd = Number.isFinite(rawWindowEnd) && rawWindowEnd > windowStart ? rawWindowEnd : 1440;
    const spans = Array.isArray(segments) && segments.length ? segments.slice().sort((left, right) => left.startMin - right.startMin) : [{ startMin: windowStart, endMin: windowEnd }];
    let totalVisible = 0;
    const meta = spans.map((s) => {
      const startMin = Math.max(windowStart, Number(s.startMin) || 0);
      const endMin = Math.min(windowEnd, Number(s.endMin) || 0);
      const span = Math.max(0, endMin - startMin);
      const cumulStart = totalVisible;
      totalVisible += span;
      return { startMin, endMin, span, cumulStart };
    });
    if (totalVisible <= 0) {
      const fallbackSpan = Math.max(1, windowEnd - windowStart);
      return function constellationMinuteToXFallback(minute) {
        const value = Number(minute);
        const offset = Number.isFinite(value) ? value - windowStart : 0;
        return CONSTELLATION_PLOT_LEFT + offset / fallbackSpan * CONSTELLATION_PLOT_WIDTH;
      };
    }
    return function constellationMinuteToX(minute) {
      const value = Number(minute);
      const m = Number.isFinite(value) ? value : windowStart;
      for (let i = 0; i < meta.length; i += 1) {
        const seg = meta[i];
        if (m < seg.startMin) {
          return CONSTELLATION_PLOT_LEFT + seg.cumulStart / totalVisible * CONSTELLATION_PLOT_WIDTH;
        }
        if (m <= seg.endMin) {
          const offset = seg.cumulStart + (m - seg.startMin);
          return CONSTELLATION_PLOT_LEFT + offset / totalVisible * CONSTELLATION_PLOT_WIDTH;
        }
      }
      return CONSTELLATION_PLOT_LEFT + CONSTELLATION_PLOT_WIDTH;
    };
  }
  const AMBIENT_HUE = 218;
  const AMBIENT_SAT_MIN = 12;
  const AMBIENT_SAT_MAX = 24;
  const AMBIENT_LIGHT_MIN = 56;
  const AMBIENT_LIGHT_MAX = 68;
  const AMBIENT_OPACITY_MIN = 0.26;
  const AMBIENT_OPACITY_MAX = 0.45;
  const AMBIENT_RADIUS_MIN = 0.7;
  const AMBIENT_RADIUS_MAX = 1.7;
  const AMBIENT_COUNT_MIN = 120;
  const AMBIENT_COUNT_MAX = 160;
  const AMBIENT_DENSITY_LOW = 0.2;
  const AMBIENT_DENSITY_HIGH = 0.6;
  const AMBIENT_PEAK_FLOOR = 0.03;
  function _ambientInverseWeight(density) {
    const value = Number(density) || 0;
    if (value <= AMBIENT_DENSITY_LOW) return 1;
    if (value >= AMBIENT_DENSITY_HIGH) return AMBIENT_PEAK_FLOOR;
    const t = (value - AMBIENT_DENSITY_LOW) / (AMBIENT_DENSITY_HIGH - AMBIENT_DENSITY_LOW);
    const smooth = t * t * (3 - 2 * t);
    return 1 - smooth * (1 - AMBIENT_PEAK_FLOOR);
  }
  function _ambientHourWeights(stars, displayWindow, segments) {
    const density = _constellationHourDensity(stars);
    const active = _constellationActiveWindow(stars);
    const activeStartH = active.startMin / 60;
    const activeEndH = active.endMin / 60;
    const windowStartH = (Number(displayWindow?.startMin) || 0) / 60;
    const windowEndH = (Number(displayWindow?.endMin) || 1440) / 60;
    const visibleSpans = Array.isArray(segments) && segments.length ? segments : null;
    const hourOverlapsVisible = (hour) => {
      if (!visibleSpans) return true;
      const hourStartMin = hour * 60;
      const hourEndMin = (hour + 1) * 60;
      return visibleSpans.some((s) => s.startMin < hourEndMin && s.endMin > hourStartMin);
    };
    const weights = new Array(24).fill(0);
    for (let h = 0; h < 24; h += 1) {
      if (h + 1 <= windowStartH || h >= windowEndH) continue;
      if (!hourOverlapsVisible(h)) continue;
      if (h >= activeStartH && h < activeEndH) {
        weights[h] = _ambientInverseWeight(density[h]);
      } else {
        weights[h] = 1;
      }
    }
    return weights;
  }
  function _ambientSampleHour(cdf, total) {
    const target = Math.random() * total;
    for (let h = 0; h < cdf.length; h += 1) {
      if (target <= cdf[h]) return h;
    }
    return cdf.length - 1;
  }
  function _ambientConstellationStars({
    stars = [],
    window: displayWindow = CONSTELLATION_FULL_DAY_WINDOW,
    segments
  } = {}) {
    const weights = _ambientHourWeights(stars, displayWindow, segments);
    let total = 0;
    const cdf = weights.map((value) => {
      total += value;
      return total;
    });
    if (total <= 0) return [];
    const totalCount = AMBIENT_COUNT_MIN + Math.floor(Math.random() * (AMBIENT_COUNT_MAX - AMBIENT_COUNT_MIN + 1));
    const minuteToX = _constellationMinuteToX(displayWindow, segments);
    const visibleSpans = Array.isArray(segments) && segments.length ? segments : null;
    const minuteInVisible = (minute) => {
      if (!visibleSpans) return true;
      return visibleSpans.some((s) => minute >= s.startMin && minute <= s.endMin);
    };
    const placed = [];
    const attemptCap = totalCount * 4;
    for (let attempt = 0; attempt < attemptCap && placed.length < totalCount; attempt += 1) {
      const hour = _ambientSampleHour(cdf, total);
      const minute = hour * 60 + Math.random() * 60;
      if (!minuteInVisible(minute)) continue;
      const x = minuteToX(minute);
      if (x < CONSTELLATION_PLOT_LEFT - 1 || x > CONSTELLATION_PLOT_RIGHT + 1) continue;
      const y = 14 + Math.random() * 268;
      placed.push({
        x,
        y,
        radius: AMBIENT_RADIUS_MIN + Math.random() * (AMBIENT_RADIUS_MAX - AMBIENT_RADIUS_MIN),
        opacity: AMBIENT_OPACITY_MIN + Math.random() * (AMBIENT_OPACITY_MAX - AMBIENT_OPACITY_MIN),
        hue: AMBIENT_HUE,
        saturation: AMBIENT_SAT_MIN + Math.random() * (AMBIENT_SAT_MAX - AMBIENT_SAT_MIN),
        lightness: AMBIENT_LIGHT_MIN + Math.random() * (AMBIENT_LIGHT_MAX - AMBIENT_LIGHT_MIN)
      });
    }
    return placed;
  }
  function _svgEl(tag, attrs = {}) {
    const el = document.createElementNS(SVG_NS, tag);
    Object.entries(attrs).forEach(([key, value]) => {
      if (value !== null && value !== void 0) el.setAttribute(key, String(value));
    });
    return el;
  }
  function _pathFromPoints(points) {
    if (!points.length) return "";
    return points.map((point, index) => `${index === 0 ? "M" : "L"}${point[0].toFixed(1)} ${point[1].toFixed(1)}`).join(" ");
  }
  function _clampNumber(value, min, max) {
    const number = Number(value);
    if (!Number.isFinite(number)) return min;
    return Math.max(min, Math.min(max, number));
  }
  function _plotPixelFromViewBox(svg, viewBoxX, viewBoxY, viewBoxWidth = 640, viewBoxHeight = 300) {
    const rect = svg?.getBoundingClientRect?.() || {};
    const plotWidth = Number(rect.width) || Number(viewBoxWidth) || 1;
    const plotHeight = Number(rect.height) || Number(viewBoxHeight) || 1;
    const parts = String(svg?.getAttribute?.("viewBox") || `0 0 ${viewBoxWidth} ${viewBoxHeight}`).trim().split(/\s+/).map(Number);
    const minX = Number.isFinite(parts[0]) ? parts[0] : 0;
    const minY = Number.isFinite(parts[1]) ? parts[1] : 0;
    const width = Number.isFinite(parts[2]) && parts[2] > 0 ? parts[2] : Number(viewBoxWidth) || 1;
    const height = Number.isFinite(parts[3]) && parts[3] > 0 ? parts[3] : Number(viewBoxHeight) || 1;
    const preserve = String(svg?.getAttribute?.("preserveAspectRatio") || "xMidYMid meet").trim();
    if (preserve === "none" || preserve.startsWith("none ")) {
      return {
        x: (Number(viewBoxX) - minX) / width * plotWidth,
        y: (Number(viewBoxY) - minY) / height * plotHeight,
        plotWidth,
        plotHeight
      };
    }
    const scaleX = plotWidth / width;
    const scaleY = plotHeight / height;
    const scale = preserve.includes("slice") ? Math.max(scaleX, scaleY) : Math.min(scaleX, scaleY);
    const renderedWidth = width * scale;
    const renderedHeight = height * scale;
    const align = preserve.split(/\s+/)[0] || "xMidYMid";
    const offsetX = align.includes("xMin") ? 0 : align.includes("xMax") ? plotWidth - renderedWidth : (plotWidth - renderedWidth) / 2;
    const offsetY = align.includes("YMin") ? 0 : align.includes("YMax") ? plotHeight - renderedHeight : (plotHeight - renderedHeight) / 2;
    return {
      x: offsetX + (Number(viewBoxX) - minX) * scale,
      y: offsetY + (Number(viewBoxY) - minY) * scale,
      plotWidth,
      plotHeight
    };
  }
  function _heartbeatProfile({ activeCount = 0, averageCpu = 0 } = {}) {
    const cpuLoad = _clampNumber(averageCpu / 100, 0, 1);
    const runLoad = _clampNumber(activeCount * 0.12, 0, 0.45);
    const load = _clampNumber(cpuLoad + runLoad, 0, 1);
    return {
      beatIntervalMs: activeCount ? Math.max(620, 2400 - load * 1320) : 2800,
      spike: activeCount ? 13 + load * 25 : 10,
      recovery: 4 + load * 6,
      glowOpacity: 0.42 + load * 0.26,
      glowWidth: 10 + load * 7,
      beatGlowOpacity: activeCount ? 0.5 + load * 0.3 : 0.26,
      beatGlowWidth: 16 + load * 12,
      lineWidth: 1.8 + load * 0.8
    };
  }
  function _pulseBucketedCpu(activeCount, averageCpu, hasCpuSample) {
    const resolvedAverage = _clampNumber(averageCpu, 0, 100);
    if (!activeCount || !hasCpuSample) {
      pulseBucketedActiveCount = activeCount;
      pulseBucketedAverageCpu = 0;
      return 0;
    }
    if (pulseBucketedAverageCpu === null || pulseBucketedActiveCount !== activeCount || Math.abs(resolvedAverage - pulseBucketedAverageCpu) > PULSE_CPU_BUCKET_HYSTERESIS) {
      pulseBucketedAverageCpu = resolvedAverage;
    }
    pulseBucketedActiveCount = activeCount;
    return Math.round((pulseBucketedAverageCpu || 0) / 5);
  }
  function _pulseRecentCpuWindow(activeCount, averageCpu, hasCpuSample) {
    if (!activeCount) {
      pulseRecentCpuSamples.length = 0;
      return [];
    }
    if (hasCpuSample) {
      pulseRecentCpuSamples.push(_clampNumber(averageCpu, 0, 100));
      while (pulseRecentCpuSamples.length > PULSE_RECENT_CPU_SAMPLE_LIMIT) {
        pulseRecentCpuSamples.shift();
      }
    }
    return pulseRecentCpuSamples.slice();
  }
  function _formatStarStarted(value) {
    const parsed = Date.parse(String(value || ""));
    if (!Number.isFinite(parsed)) return "time unavailable";
    return new Date(parsed).toLocaleString(void 0, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit"
    });
  }
  function _heatmapCalendarDays(activityDays, firstRunDate) {
    const sourceDays = (Array.isArray(activityDays) ? activityDays : []).filter((day) => _parseIsoDateOnly(day?.date) !== null);
    if (!sourceDays.length) {
      return { cells: [], weekCount: 0 };
    }
    const firstSource = _parseIsoDateOnly(sourceDays[0].date);
    const lastSource = _parseIsoDateOnly(sourceDays[sourceDays.length - 1].date);
    if (firstSource === null || lastSource === null) {
      return { cells: [], weekCount: 0 };
    }
    const leadingDays = _isoWeekdayRow(firstSource) - 1;
    const gridStart = firstSource - leadingDays * DAY_MS;
    const totalSourceDays = Math.max(1, Math.round((lastSource - firstSource) / DAY_MS) + 1);
    const weekCount = Math.max(4, Math.ceil((leadingDays + totalSourceDays) / 7));
    const byDate = new Map(sourceDays.map((day) => [String(day.date), day]));
    const firstRun = _parseIsoDateOnly(firstRunDate);
    const cells = [];
    for (let index = 0; index < weekCount * 7; index += 1) {
      const timestamp = gridStart + index * DAY_MS;
      const date = _formatIsoDateOnly(timestamp);
      const source = byDate.get(date);
      const inSourceWindow = timestamp >= firstSource && timestamp <= lastSource;
      cells.push({
        ...source || { date, count: 0, succeeded: 0, failed: 0, incomplete: 0 },
        date,
        column: Math.floor(index / 7) + 1,
        row: index % 7 + 1,
        inSourceWindow,
        outOfRange: !inSourceWindow || firstRun === null || timestamp < firstRun
      });
    }
    return { cells, weekCount };
  }
  function _monthShortLabel(date) {
    const timestamp = _parseIsoDateOnly(date);
    if (timestamp === null) return "";
    return new Date(timestamp).toLocaleString(void 0, {
      month: "short",
      timeZone: "UTC"
    });
  }
  function _heatmapMonthMarkers(calendar) {
    const seenMonths = /* @__PURE__ */ new Set();
    return (calendar?.cells || []).reduce((markers, day) => {
      if (!day?.inSourceWindow) return markers;
      const monthKey = String(day.date || "").slice(0, 7);
      if (seenMonths.has(monthKey)) return markers;
      const dayOfMonth = String(day.date || "").slice(8, 10);
      if (dayOfMonth !== "01" && markers.length) return markers;
      seenMonths.add(monthKey);
      markers.push({ label: _monthShortLabel(day.date), column: day.column });
      return markers;
    }, []);
  }
  function _heatmapPopoverText(day) {
    const count = Number(day?.count || 0);
    return {
      root: String(day?.date || "day"),
      command: `${_formatCount(count)} ${count === 1 ? "run" : "runs"}`,
      success: `${_formatCount(day?.succeeded || 0)} success`,
      fail: `${_formatCount(day?.failed || 0)} fail`,
      incomplete: `${_formatCount(day?.incomplete || 0)} incomplete`,
      range: day?.outOfRange ? "outside range" : "in range"
    };
  }
  function _showHeatmapPopover(panel, day, cell, event = null) {
    const popover = panel.querySelector(".status-monitor-constellation-popover");
    if (!popover || !cell) return;
    const plot = popover.parentElement;
    const fields = _heatmapPopoverText(day);
    popover.querySelector('[data-field="root"]').textContent = fields.root;
    popover.querySelector('[data-field="command"]').textContent = fields.command;
    popover.querySelector('[data-field="time"]').textContent = fields.success;
    popover.querySelector('[data-field="duration"]').textContent = fields.fail;
    popover.querySelector('[data-field="exit"]').textContent = fields.incomplete;
    popover.querySelector('[data-field="lines"]').textContent = fields.range;
    const plotRect = plot?.getBoundingClientRect?.() || {};
    const cellRect = cell.getBoundingClientRect?.() || {};
    const plotWidth = Number(plotRect.width) || 280;
    const plotHeight = Number(plotRect.height) || 90;
    const hasPointer = event && Number.isFinite(Number(event.clientX)) && Number.isFinite(Number(event.clientY));
    const targetX = hasPointer ? Number(event.clientX) - Number(plotRect.left || 0) : Number(cellRect.left) - Number(plotRect.left || 0) + Number(cellRect.width) / 2;
    const targetY = hasPointer ? Number(event.clientY) - Number(plotRect.top || 0) : Number(cellRect.top) - Number(plotRect.top || 0) + Number(cellRect.height) / 2;
    const popoverRect = popover.getBoundingClientRect?.() || {};
    const fallbackWidth = Math.min(280, Math.max(1, plotWidth - 22));
    const popoverWidth = popover.offsetWidth || Number(popoverRect.width) || fallbackWidth;
    const popoverHeight = popover.offsetHeight || Number(popoverRect.height) || 92;
    const margin = 8;
    const gap = 14;
    const maxLeft = Math.max(margin, plotWidth - popoverWidth - margin);
    const maxTop = Math.max(margin, plotHeight - popoverHeight - margin);
    const roomRight = plotWidth - targetX - margin;
    const placeLeft = roomRight < popoverWidth + gap && targetX > popoverWidth + gap + margin;
    const preferredLeft = placeLeft ? targetX - popoverWidth - gap : targetX + gap;
    const left = _clampNumber(preferredLeft, margin, maxLeft);
    const preferredTop = targetY - popoverHeight / 2;
    const top = _clampNumber(preferredTop, margin, maxTop);
    popover.style.left = `${left.toFixed(1)}px`;
    popover.style.top = `${top.toFixed(1)}px`;
    popover.classList.toggle("status-monitor-constellation-popover-below", false);
    popover.classList.add("status-monitor-constellation-popover-visible");
    popover.setAttribute("aria-hidden", "false");
  }
  function _formatPercent(value) {
    if (!_isTelemetryNumber(value)) return "0%";
    const number = Math.max(0, Math.min(100, Number(value)));
    return `${number.toFixed(number >= 10 ? 0 : 1)}%`;
  }
  function _statusLabel(value) {
    const normalized = String(value || "").trim().toLowerCase();
    if (normalized === "ok") return "online";
    if (normalized === "down") return "down";
    if (normalized === "none") return "not configured";
    return normalized || "unknown";
  }
  function _statusTone(value) {
    const normalized = String(value || "").trim().toLowerCase();
    if (normalized === "ok") return "ok";
    if (normalized === "none") return "idle";
    if (normalized === "down") return "bad";
    return "warn";
  }
  function _memoryPercent(value) {
    if (!_isTelemetryNumber(value)) return null;
    const gibibyte = 1024 * 1024 * 1024;
    return Math.min(100, Math.max(0, Number(value) / gibibyte * 100));
  }
  function _meterPercent(value) {
    if (!_isTelemetryNumber(value)) return 0;
    return Math.min(100, Math.max(0, Number(value)));
  }
  function _statusMonitorMeter({ label, value, percent, className = "", collecting = false, ariaValue = value }) {
    const meter = document.createElement("div");
    meter.className = `status-monitor-meter ${className} ${collecting ? "status-monitor-meter-collecting" : ""}`.trim();
    meter.style.setProperty("--meter-percent", `${collecting ? 75 : _meterPercent(percent)}%`);
    meter.setAttribute("aria-label", `${label} ${ariaValue}`);
    const labelEl = document.createElement("span");
    labelEl.className = "status-monitor-meter-label";
    labelEl.textContent = label;
    const ring = document.createElement("span");
    ring.className = "status-monitor-meter-ring";
    const valueEl = document.createElement("span");
    valueEl.className = "status-monitor-meter-value";
    valueEl.textContent = value;
    ring.append(valueEl);
    meter.append(labelEl, ring);
    return meter;
  }
  function _updateStatusMonitorMeter(meter, { label, value, percent, collecting = false, ariaValue = value }) {
    meter.classList.toggle("status-monitor-meter-collecting", collecting);
    const nextPercent = `${collecting ? 75 : _meterPercent(percent)}%`;
    if (meter.style.getPropertyValue("--meter-percent") !== nextPercent) {
      meter.style.setProperty("--meter-percent", nextPercent);
    }
    const ariaLabel = `${label} ${ariaValue}`;
    if (meter.getAttribute("aria-label") !== ariaLabel) {
      meter.setAttribute("aria-label", ariaLabel);
    }
    const valueEl = meter.querySelector(".status-monitor-meter-value");
    if (valueEl && valueEl.textContent !== String(value)) {
      valueEl.textContent = String(value);
    }
  }
  function _tabForRun(run) {
    const runId = String(run?.run_id || run?.id || "");
    const currentTabs = typeof getTabsFn === "function" ? getTabsFn() : [];
    if (!runId || !Array.isArray(currentTabs)) return null;
    return currentTabs.find((candidate) => candidate && (candidate.runId === runId || candidate.historyRunId === runId)) || null;
  }
  function _isPtyRun(run) {
    return String(run?.run_type || "").toLowerCase() === "pty";
  }
  function _ptyAttachUnavailableMessage(run) {
    if (!_isPtyRun(run) || _tabForRun(run)) return "";
    if (typeof _attachInteractivePtyCommand() === "function") return "";
    return "Interactive PTY is still running, but this browser cannot attach to the live terminal. Use Status Monitor to track or kill it.";
  }
  function _tabLabelForRun(run) {
    const tab = _tabForRun(run);
    if (!tab) return "";
    return String(tab.label || tab.command || tab.id || "").trim();
  }
  function _statusMonitorActionButton(label, title, onClick, options = {}) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-secondary btn-compact status-monitor-action-btn";
    if (options.className) btn.classList.add(...String(options.className).split(/\s+/).filter(Boolean));
    btn.textContent = label;
    btn.title = title;
    btn.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const result = onClick();
      Promise.resolve(result).then((attached) => {
        if (attached && options.closeOnSuccess !== false) closeStatusMonitor();
      }).catch((err) => {
        if (typeof showToastFn === "function") {
          showToastFn(err?.message || "Could not complete run action", "error");
        }
      });
    });
    return btn;
  }
  function _openHistoryForCommandRoot(root) {
    const commandRoot = String(root || "").trim();
    if (!commandRoot) return false;
    if (typeof openHistoryWithFiltersFn !== "function") {
      if (typeof showToastFn === "function") showToastFn("History filtering is not available", "error");
      return false;
    }
    openHistoryWithFiltersFn({ type: "runs", commandRoot });
    closeStatusMonitor();
    return true;
  }
  function _restoreConstellationRun(star) {
    const runId = String(star?.id || "").trim();
    if (!runId) return Promise.resolve(false);
    if (typeof restoreHistoryRunFn !== "function") {
      if (typeof showToastFn === "function") showToastFn("Run restore is not available", "error");
      return Promise.resolve(false);
    }
    return Promise.resolve(restoreHistoryRunFn(runId, { hidePanelOnSuccess: false })).then(() => {
      closeStatusMonitor();
      return true;
    }).catch((err) => {
      if (typeof showToastFn === "function") {
        showToastFn(err?.message || "Failed to restore run", "error");
      }
      return false;
    });
  }
  function _clearDocumentSelection() {
    const selection = window.getSelection?.();
    if (selection && typeof selection.removeAllRanges === "function") {
      selection.removeAllRanges();
    }
  }
  function _positionMonitor() {
    const rail = document.getElementById("rail");
    const right = rail ? Math.ceil(rail.getBoundingClientRect().right) : 0;
    const hud = document.getElementById("hud");
    const hudBottom = hud ? Math.ceil(window.innerHeight - hud.getBoundingClientRect().top) : 46;
    document.documentElement.style.setProperty("--status-monitor-left", `${right}px`);
    document.documentElement.style.setProperty("--status-monitor-bottom", `${hudBottom}px`);
  }
  function _updateElapsedTimers() {
    document.querySelectorAll("[data-status-monitor-started]").forEach((el) => {
      el.textContent = _formatElapsed(el.getAttribute("data-status-monitor-started"));
    });
  }
  function _updateLiveUptimeDisplays() {
    const uptime = _statusMonitorUptimeText();
    document.querySelectorAll("[data-status-monitor-uptime-value]").forEach((el) => {
      if (el.textContent !== uptime) el.textContent = uptime;
    });
    const prefix = summaryEl?.dataset?.statusMonitorSummaryPrefix;
    if (summaryEl && prefix) {
      const text = `${prefix} · ${uptime} uptime`;
      if (summaryEl.textContent !== text) summaryEl.textContent = text;
    }
  }
  async function _loadActiveRuns() {
    return _statusMonitorData().loadActiveRuns();
  }
  async function _loadSystemStatus() {
    return _statusMonitorData().loadSystemStatus();
  }
  async function _loadWorkspaceStatus() {
    return _statusMonitorData().loadWorkspaceStatus();
  }
  async function _loadSessionStats() {
    return _statusMonitorData().loadSessionStats();
  }
  async function _loadHistoryInsights() {
    return _statusMonitorData().loadHistoryInsights();
  }
  async function _refreshHistoryInsights() {
    cachedInsights = await _statusMonitorData().refreshHistoryInsights();
    return cachedInsights;
  }
  async function _refreshDashboardData({ includeInsights = false } = {}) {
    const data = await _statusMonitorData().refreshDashboardData({
      cachedInsights,
      includeInsights
    });
    cachedStatus = data.status;
    cachedWorkspace = data.workspace;
    cachedStats = data.stats;
    if (data.loadedInsights) cachedInsights = data.insights;
  }
  async function _refreshActiveRunCache({ render = false, renderWhileOpen = true } = {}) {
    const runs = await _loadActiveRuns();
    cachedRuns = runs;
    runs.forEach((run) => _runResourceUsage(run));
    if (render || renderWhileOpen && isOpen) _renderDashboard(runs);
    if (!runs.length) {
      _statusMonitorResources().clear();
      _stopClosedPolling();
    }
    return runs;
  }
  function _ensureMonitor() {
    if (monitorEl && scrimEl && listEl && summaryEl) return;
    scrimEl = document.createElement("div");
    scrimEl.className = "status-monitor-scrim u-hidden";
    scrimEl.setAttribute("aria-hidden", "true");
    scrimEl.addEventListener("click", () => closeStatusMonitor());
    monitorEl = document.createElement("aside");
    monitorEl.id = "status-monitor";
    monitorEl.className = "status-monitor status-monitor-modal chrome-drawer mobile-sheet-surface u-hidden";
    monitorEl.setAttribute("role", "dialog");
    monitorEl.setAttribute("aria-modal", "true");
    monitorEl.setAttribute("aria-labelledby", "status-monitor-title");
    const header = document.createElement("div");
    header.className = "status-monitor-header surface-header";
    const titleWrap = document.createElement("div");
    const title = document.createElement("div");
    title.id = "status-monitor-title";
    title.className = "status-monitor-title";
    title.textContent = "Status Monitor";
    summaryEl = document.createElement("div");
    summaryEl.className = "status-monitor-summary";
    summaryEl.textContent = "Loading...";
    titleWrap.append(title, summaryEl);
    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "status-monitor-close";
    closeBtn.setAttribute("aria-label", "Close status monitor");
    const closeIcon = document.createElement("span");
    closeIcon.className = "status-monitor-collapse-glyph";
    closeIcon.setAttribute("aria-hidden", "true");
    closeIcon.textContent = "✕";
    closeBtn.appendChild(closeIcon);
    closeBtn.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      closeStatusMonitor();
    });
    header.append(titleWrap, closeBtn);
    listEl = document.createElement("div");
    listEl.className = "status-monitor-list surface-body";
    monitorEl.append(header, listEl);
    monitorEl.addEventListener("click", (event) => event.stopPropagation());
    document.body.append(scrimEl, monitorEl);
    if (typeof bindFocusTrapFn === "function") bindFocusTrapFn(monitorEl);
    if (typeof bindDismissibleFn === "function") {
      bindDismissibleFn(monitorEl, {
        level: "modal",
        isOpen: () => isOpen,
        onClose: () => closeStatusMonitor(),
        backdropEl: scrimEl,
        closeButtons: closeBtn
      });
    }
    if (typeof bindMobileSheetFn === "function") {
      bindMobileSheetFn(monitorEl, { onClose: () => closeStatusMonitor() });
    }
  }
  function _statusSection(title, meta = "") {
    const section = document.createElement("section");
    section.className = "status-monitor-section";
    const header = document.createElement("div");
    header.className = "status-monitor-section-header";
    const titleEl = document.createElement("div");
    titleEl.className = "status-monitor-section-title";
    titleEl.textContent = title;
    header.appendChild(titleEl);
    if (meta) {
      const metaEl = document.createElement("div");
      metaEl.className = "status-monitor-section-meta";
      metaEl.textContent = meta;
      header.appendChild(metaEl);
    }
    section.appendChild(header);
    return section;
  }
  function _statusCard({ label, value, meta = "", tone = "", meterPercent = null, compact = false, valueDataset = null }) {
    const card = document.createElement("div");
    card.className = `status-monitor-card ${tone ? `status-monitor-card-${tone}` : ""} ${compact ? "status-monitor-card-compact" : ""}`.trim();
    const labelEl = document.createElement("div");
    labelEl.className = "status-monitor-card-label";
    labelEl.textContent = label;
    const valueRow = document.createElement("div");
    valueRow.className = "status-monitor-card-value-row";
    if (tone) {
      const dot = document.createElement("span");
      dot.className = `status-monitor-dot status-monitor-dot-${tone}`;
      dot.setAttribute("aria-hidden", "true");
      valueRow.appendChild(dot);
    }
    const valueEl = document.createElement("div");
    valueEl.className = "status-monitor-card-value";
    valueEl.textContent = value;
    if (valueDataset && typeof valueDataset === "object") {
      Object.entries(valueDataset).forEach(([key, datasetValue]) => {
        valueEl.dataset[key] = String(datasetValue);
      });
    }
    valueRow.appendChild(valueEl);
    card.append(labelEl, valueRow);
    if (meta) {
      const metaEl = document.createElement("div");
      metaEl.className = "status-monitor-card-meta";
      metaEl.textContent = meta;
      card.appendChild(metaEl);
    }
    if (_isTelemetryNumber(meterPercent)) {
      const bar = document.createElement("div");
      bar.className = "status-monitor-card-meter";
      bar.style.setProperty("--status-meter-percent", `${_meterPercent(meterPercent)}%`);
      card.appendChild(bar);
    }
    return card;
  }
  function _statusGrid(cards, className = "") {
    const grid = document.createElement("div");
    grid.className = `status-monitor-grid ${className}`.trim();
    cards.filter(Boolean).forEach((card) => grid.appendChild(card));
    return grid;
  }
  function _pulseStripData(runs) {
    const status = cachedStatus || {};
    const activeRuns = Array.isArray(runs) ? runs : [];
    const cpuValues = [];
    activeRuns.forEach((run) => {
      const state = _statusMonitorResources().getState(String(run?.run_id || run?.id || ""));
      if (_isTelemetryNumber(state?.cpu_percent)) {
        cpuValues.push(Math.max(0, Number(state.cpu_percent)));
      }
    });
    const avgCpu = cpuValues.length ? cpuValues.reduce((total, value) => total + value, 0) / cpuValues.length : 0;
    const cpuSamples = _pulseRecentCpuWindow(activeRuns.length, avgCpu, cpuValues.length > 0);
    const signatureCpuBucket = _pulseBucketedCpu(activeRuns.length, avgCpu, cpuValues.length > 0);
    const cpuMeta = activeRuns.length && cpuValues.length ? ` · ${_formatCpuPercent(avgCpu)} avg CPU` : "";
    const profile = _heartbeatProfile({ activeCount: activeRuns.length, averageCpu: avgCpu });
    const summaryPrefix = `${activeRuns.length} active${cpuMeta}`;
    return {
      signature: `${activeRuns.length}:${signatureCpuBucket}`,
      activeCount: activeRuns.length,
      averageCpu: avgCpu,
      cpuSamples,
      ...profile,
      summaryPrefix,
      meta: `${summaryPrefix} · ${_statusMonitorUptimeText(status)} uptime`
    };
  }
  function _pulseLoadTier(averageCpu, hasCpuSample, activeCount) {
    if (!activeCount || !hasCpuSample) {
      return {
        name: "idle",
        color: "var(--green)",
        alpha: 0.1,
        borderAlpha: 0.28,
        shadowAlpha: 0.08
      };
    }
    const cpu = _clampNumber(averageCpu, 0, 100);
    if (cpu >= 85) {
      return {
        name: "very-heavy",
        color: "var(--red)",
        alpha: 0.34,
        borderAlpha: 0.58,
        shadowAlpha: 0.2
      };
    }
    if (cpu >= 65) {
      return {
        name: "heavy",
        color: "var(--orange, #ff7a18)",
        alpha: 0.3,
        borderAlpha: 0.52,
        shadowAlpha: 0.18
      };
    }
    if (cpu >= 35) {
      return {
        name: "busy",
        color: "var(--amber)",
        alpha: 0.24,
        borderAlpha: 0.45,
        shadowAlpha: 0.15
      };
    }
    return {
      name: "light",
      color: "var(--green)",
      alpha: 0.16,
      borderAlpha: 0.34,
      shadowAlpha: 0.1
    };
  }
  function _applyPulseLoadStyle(strip, data) {
    if (!strip) return;
    const hasCpuSample = Array.isArray(data?.cpuSamples) && data.cpuSamples.length > 0;
    const tier = suppressPulseLoadUntilFresh ? _pulseLoadTier(0, false, 0) : _pulseLoadTier(data?.averageCpu || 0, hasCpuSample, data?.activeCount || 0);
    strip.dataset.pulseLoad = tier.name;
    strip.style.setProperty("--pulse-load-color", tier.color);
    strip.style.setProperty("--pulse-load-alpha", tier.alpha.toFixed(2));
    strip.style.setProperty("--pulse-load-border-alpha", tier.borderAlpha.toFixed(2));
    strip.style.setProperty("--pulse-load-shadow-alpha", tier.shadowAlpha.toFixed(2));
  }
  function _pulseBeatPoints(beat) {
    const baseline = PULSE_BASELINE_Y;
    const x = beat.x;
    return [
      [x - 8, baseline],
      [x - 1, baseline],
      [x + 3, baseline + beat.recovery],
      [x + 8, baseline - beat.spike],
      [x + 13, baseline + beat.spike * 0.56],
      [x + 19, baseline],
      [x + 25, baseline - beat.recovery * 0.72],
      [x + 34, baseline]
    ];
  }
  function _visiblePulseBeats(beats, offset = 0) {
    return beats.filter((beat) => {
      const renderedX = beat.x - offset;
      return renderedX > -70 && renderedX < PULSE_VIEW_WIDTH + 70;
    }).sort((left, right) => left.x - right.x);
  }
  function _renderablePulseBeats(beats, offset = 0) {
    const rendered = [];
    let lastBeatEnd = -Infinity;
    _visiblePulseBeats(beats, offset).forEach((beat) => {
      const beatStart = beat.x - 8;
      const beatEnd = beat.x + 34;
      if (beatEnd < offset - PULSE_PATH_MARGIN) return;
      if (beatStart <= lastBeatEnd + 2) return;
      rendered.push(beat);
      lastBeatEnd = beatEnd;
    });
    return rendered;
  }
  function _pulsePathFromBeats(beats, viewportStart = 0, viewportEnd = PULSE_VIEW_WIDTH, options = {}) {
    const points = [];
    const pathStart = _isTelemetryNumber(options.pathStart) ? Number(options.pathStart) : viewportStart - PULSE_PATH_MARGIN;
    const pathEnd = _isTelemetryNumber(options.pathEnd) ? Number(options.pathEnd) : viewportEnd + PULSE_PATH_MARGIN;
    beats.forEach((beat) => {
      const beatPoints = _pulseBeatPoints(beat);
      if (!points.length && beatPoints[0][0] > pathStart) {
        points.push([pathStart, PULSE_BASELINE_Y]);
      }
      if (points.length && beatPoints[0][0] < points[points.length - 1][0]) return;
      points.push(...beatPoints);
    });
    if (!points.length) {
      points.push([pathStart, PULSE_BASELINE_Y]);
    }
    if (points[points.length - 1][0] < pathEnd) {
      points.push([pathEnd, PULSE_BASELINE_Y]);
    }
    return _pathFromPoints(points);
  }
  function _pulsePlaceholderPath(pathStart, pathEnd) {
    if (pathEnd <= pathStart) return "";
    const width = pathEnd - pathStart;
    const step = Math.max(10, Math.min(20, width / 32));
    const points = [];
    for (let x = pathStart; x < pathEnd; x += step) {
      const progress = (x - pathStart) / width;
      const wave = Math.sin(progress * Math.PI * 8) * Math.sin(progress * Math.PI);
      points.push([x, PULSE_BASELINE_Y + wave * 1.4]);
    }
    points.push([pathEnd, PULSE_BASELINE_Y]);
    return _pathFromPoints(points);
  }
  function _pulseBeatGlowPath(beat) {
    return _pathFromPoints(_pulseBeatPoints(beat));
  }
  function _pulseGlowGroups(beats) {
    const groups = /* @__PURE__ */ new Map();
    beats.forEach((beat) => {
      const key = [
        beat.glowOpacity.toFixed(2),
        beat.glowWidth.toFixed(1),
        beat.beatGlowOpacity.toFixed(2),
        beat.beatGlowWidth.toFixed(1)
      ].join(":");
      const group = groups.get(key) || {
        key,
        glowOpacity: beat.glowOpacity,
        glowWidth: beat.glowWidth,
        beatGlowOpacity: beat.beatGlowOpacity,
        beatGlowWidth: beat.beatGlowWidth,
        paths: []
      };
      group.paths.push(_pulseBeatGlowPath(beat));
      groups.set(key, group);
    });
    return groups;
  }
  function _syncPulseGlowGroup(groupEl, groups, className, styleFor) {
    if (!groupEl) return;
    const existing = new Map(
      [...groupEl.children].map((child) => [child.dataset.pulseGlowKey, child])
    );
    const seen = /* @__PURE__ */ new Set();
    groups.forEach((group) => {
      let path = existing.get(group.key);
      if (!path) {
        path = _svgEl("path", { class: className });
        path.dataset.pulseGlowKey = group.key;
        groupEl.appendChild(path);
      }
      path.setAttribute("d", group.paths.join(" "));
      path.setAttribute("style", styleFor(group));
      seen.add(group.key);
    });
    existing.forEach((path, key) => {
      if (!seen.has(key)) path.remove();
    });
  }
  function _pulseGlowRenderScale() {
    if (!_isMobileStatusMonitor()) {
      return {
        glowWidth: 1,
        glowOpacity: 1,
        glowMinWidth: 1,
        glowMinOpacity: 0,
        beatGlowWidth: 1,
        beatGlowOpacity: 1,
        beatGlowMinWidth: 1,
        beatGlowMinOpacity: 0
      };
    }
    return {
      glowWidth: 1,
      glowOpacity: 1,
      glowMinWidth: 6,
      glowMinOpacity: 0.3,
      beatGlowWidth: 0.16,
      beatGlowOpacity: 0.2,
      beatGlowMinWidth: 2.5,
      beatGlowMinOpacity: 0.08
    };
  }
  function _renderMobilePulseGlowEllipses(groupEl, beats, gradientId) {
    if (!groupEl || !gradientId) return;
    const fragment = document.createDocumentFragment();
    beats.forEach((beat) => {
      const load = _clampNumber((Number(beat.spike || 0) - 10) / 28, 0, 1);
      const points = _pulseBeatPoints(beat);
      const xs = points.map((point) => point[0]);
      const ys = points.map((point) => point[1]);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      const beatHeight = Math.max(1, maxY - minY);
      const smallBeatBoost = (1 - load) * 8;
      const radius = beatHeight * 0.62 + 6 + load * 4 + smallBeatBoost;
      const weighted = points.reduce((acc, point) => {
        const weight = Math.abs(point[1] - PULSE_BASELINE_Y);
        if (!weight) return acc;
        acc.x += point[0] * weight;
        acc.y += point[1] * weight;
        acc.weight += weight;
        return acc;
      }, { x: 0, y: 0, weight: 0 });
      const centerX = weighted.weight ? weighted.x / weighted.weight : (minX + maxX) / 2;
      const weightedCenterY = weighted.weight ? weighted.y / weighted.weight : (minY + maxY) / 2;
      const centerY = weightedCenterY * 0.38 + PULSE_BASELINE_Y * 0.62;
      const ellipse = _svgEl("ellipse", {
        class: "status-monitor-pulse-mobile-glow",
        cx: centerX.toFixed(1),
        cy: centerY.toFixed(1),
        rx: radius.toFixed(1),
        ry: (radius * 1.08).toFixed(1),
        opacity: _clampNumber(0.64 + load * 0.22 + (1 - load) * 0.04, 0.64, 0.86).toFixed(2),
        fill: `url(#${gradientId})`
      });
      fragment.appendChild(ellipse);
    });
    groupEl.replaceChildren(fragment);
  }
  function _pulseNodes(strip) {
    let nodes = pulseNodeCacheByStrip.get(strip);
    if (!nodes) {
      nodes = {
        track: strip.querySelector(".status-monitor-pulse-track"),
        broadGroup: strip.querySelector(".status-monitor-pulse-glows"),
        beatGroup: strip.querySelector(".status-monitor-pulse-beat-glows"),
        placeholderLine: strip.querySelector(".status-monitor-pulse-placeholder-line"),
        line: strip.querySelector(".status-monitor-pulse-line")
      };
      pulseNodeCacheByStrip.set(strip, nodes);
    }
    return nodes;
  }
  function _renderPulseBeatGlows(strip, beats) {
    const { broadGroup, beatGroup } = _pulseNodes(strip);
    if (!broadGroup || !beatGroup) return;
    const groups = _pulseGlowGroups(beats);
    const scale = _pulseGlowRenderScale();
    if (_isMobileStatusMonitor()) {
      _renderMobilePulseGlowEllipses(broadGroup, beats, strip.dataset.pulseGlowGradientId || "");
    } else {
      _syncPulseGlowGroup(broadGroup, groups, "status-monitor-pulse-glow", (group) => [
        `--pulse-glow-opacity:${Math.max(scale.glowMinOpacity, group.glowOpacity * scale.glowOpacity).toFixed(2)}`,
        `--pulse-glow-width:${Math.max(scale.glowMinWidth, group.glowWidth * scale.glowWidth).toFixed(1)}px`
      ].join(";"));
    }
    _syncPulseGlowGroup(beatGroup, groups, "status-monitor-pulse-beat-glow", (group) => [
      `--pulse-beat-glow-opacity:${Math.max(scale.beatGlowMinOpacity, group.beatGlowOpacity * scale.beatGlowOpacity).toFixed(2)}`,
      `--pulse-beat-glow-width:${Math.max(scale.beatGlowMinWidth, group.beatGlowWidth * scale.beatGlowWidth).toFixed(1)}px`
    ].join(";"));
  }
  function _pulseBeatFromData(x, data, index = 0) {
    const cpuSamples = Array.isArray(data.cpuSamples) && data.cpuSamples.length ? data.cpuSamples : [data.averageCpu || 0];
    const sampleCpu = cpuSamples[Math.abs(index) % cpuSamples.length];
    const profile = _heartbeatProfile({ activeCount: data.activeCount, averageCpu: sampleCpu });
    return {
      x,
      spike: profile.spike,
      recovery: profile.recovery,
      glowOpacity: profile.glowOpacity,
      glowWidth: profile.glowWidth,
      beatGlowOpacity: profile.beatGlowOpacity,
      beatGlowWidth: profile.beatGlowWidth
    };
  }
  function _pulseNow() {
    return window.performance && typeof window.performance.now === "function" ? window.performance.now() : Date.now();
  }
  function _seedPulseState(data, options = {}) {
    const intervalPx = data.beatIntervalMs * PULSE_SCROLL_PX_PER_MS;
    const beats = [];
    let beatCursor = 0;
    const fresh = !!options.fresh;
    const liveStartX = fresh ? PULSE_VIEW_WIDTH - PULSE_FRESH_LIVE_WINDOW : -intervalPx;
    if (fresh) {
      beats.push(_pulseBeatFromData(liveStartX + 42, data, beatCursor));
      beatCursor += 1;
    } else {
      for (let x = -intervalPx; x < PULSE_VIEW_WIDTH + intervalPx; x += intervalPx) {
        beats.push(_pulseBeatFromData(x, data, beatCursor));
        beatCursor += 1;
      }
    }
    return {
      beats,
      beatCursor,
      lastFrameAt: null,
      liveStartX,
      latestProfile: data,
      nextBeatInMs: fresh ? data.beatIntervalMs * 0.45 : data.beatIntervalMs,
      offset: 0,
      geometryDirty: true,
      signature: data.signature
    };
  }
  function _ensurePulseState(strip, data) {
    let state = pulseStateByStrip.get(strip);
    if (!state) {
      state = _seedPulseState(data, { fresh: true });
      pulseStateByStrip.set(strip, state);
    }
    if (state.signature !== data.signature) {
      state.nextBeatInMs = Math.min(state.nextBeatInMs, data.beatIntervalMs * 0.35);
      state.signature = data.signature;
    }
    state.latestProfile = data;
    return state;
  }
  function _resetPulseVisualsForOpen() {
    pulseRecentCpuSamples.length = 0;
    pulseBucketedAverageCpu = null;
    pulseBucketedActiveCount = null;
    const idleTier = _pulseLoadTier(0, false, 0);
    document.querySelectorAll(".status-monitor-pulse-strip").forEach((strip) => {
      strip.classList.add("status-monitor-pulse-load-resetting");
      pulseStateByStrip.delete(strip);
      const nodes = _pulseNodes(strip);
      nodes.placeholderLine?.setAttribute("d", "");
      nodes.line?.setAttribute("d", "");
      nodes.broadGroup?.replaceChildren();
      nodes.beatGroup?.replaceChildren();
      nodes.track?.setAttribute("transform", "translate(0 0)");
      strip.dataset.pulseLoad = idleTier.name;
      strip.style.setProperty("--pulse-load-color", idleTier.color);
      strip.style.setProperty("--pulse-load-alpha", idleTier.alpha.toFixed(2));
      strip.style.setProperty("--pulse-load-border-alpha", idleTier.borderAlpha.toFixed(2));
      strip.style.setProperty("--pulse-load-shadow-alpha", idleTier.shadowAlpha.toFixed(2));
      void strip.offsetWidth;
      strip.classList.remove("status-monitor-pulse-load-resetting");
    });
  }
  function _renderPulseState(strip, timestamp) {
    const state = pulseStateByStrip.get(strip);
    if (!state) return;
    const nodes = _pulseNodes(strip);
    const now = Number.isFinite(Number(timestamp)) ? Number(timestamp) : _pulseNow();
    const previous = state.lastFrameAt ?? now;
    const deltaMs = Math.max(0, Math.min(100, now - previous));
    state.lastFrameAt = now;
    if (deltaMs > 0) {
      const distance = deltaMs * PULSE_SCROLL_PX_PER_MS;
      state.offset = (state.offset || 0) + distance;
      state.nextBeatInMs -= deltaMs;
      while (state.nextBeatInMs <= 0) {
        state.beats.push(_pulseBeatFromData(
          (state.offset || 0) + PULSE_VIEW_WIDTH + 52,
          state.latestProfile,
          state.beatCursor || 0
        ));
        state.beatCursor = (state.beatCursor || 0) + 1;
        state.nextBeatInMs += state.latestProfile.beatIntervalMs;
        state.geometryDirty = true;
      }
      const remainingBeats = state.beats.filter((beat) => beat.x - (state.offset || 0) > -76);
      if (remainingBeats.length !== state.beats.length) {
        state.beats = remainingBeats;
        state.geometryDirty = true;
      }
    }
    const offset = state.offset || 0;
    if (state.geometryDirty) {
      const renderableBeats = _renderablePulseBeats(state.beats, offset);
      const liveStartX = _isTelemetryNumber(state.liveStartX) ? Number(state.liveStartX) : offset - PULSE_PATH_MARGIN;
      const placeholderEnd = Math.min(liveStartX, offset + PULSE_VIEW_WIDTH + PULSE_PATH_MARGIN);
      const placeholderPath = placeholderEnd > offset - PULSE_PATH_MARGIN ? _pulsePlaceholderPath(offset - PULSE_PATH_MARGIN, placeholderEnd) : "";
      const path = _pulsePathFromBeats(renderableBeats, offset, offset + PULSE_VIEW_WIDTH, {
        pathStart: Math.max(liveStartX, offset - PULSE_PATH_MARGIN),
        pathEnd: offset + PULSE_VIEW_WIDTH + PULSE_PATH_MARGIN
      });
      _renderPulseBeatGlows(strip, renderableBeats);
      nodes.placeholderLine?.setAttribute("d", placeholderPath);
      nodes.line?.setAttribute("d", path);
      state.geometryDirty = false;
    }
    nodes.track?.setAttribute("transform", `translate(${-offset.toFixed(1)} 0)`);
  }
  function _renderPulseStrips(timestamp) {
    document.querySelectorAll(".status-monitor-pulse-strip").forEach((strip) => {
      _renderPulseState(strip, timestamp);
    });
  }
  function _pulseMotionReduced() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }
  function _requestPulseFrame(callback) {
    if (typeof window.requestAnimationFrame === "function") {
      return { type: "raf", id: window.requestAnimationFrame(callback) };
    }
    return { type: "timer", id: window.setTimeout(() => callback(_pulseNow()), 16) };
  }
  function _cancelPulseFrame(handle) {
    if (!handle) return;
    if (handle.type === "raf" && typeof window.cancelAnimationFrame === "function") {
      window.cancelAnimationFrame(handle.id);
      return;
    }
    window.clearTimeout(handle.id);
  }
  function _startPulseAnimation() {
    if (pulseAnimationFrame || _pulseMotionReduced()) return;
    const frame = (timestamp) => {
      pulseAnimationFrame = null;
      if (!isOpen || document.visibilityState !== "visible") return;
      if (lastPulseRenderAt === null || timestamp - lastPulseRenderAt >= PULSE_FRAME_MS) {
        lastPulseRenderAt = timestamp;
        _renderPulseStrips(timestamp);
      }
      pulseAnimationFrame = _requestPulseFrame(frame);
    };
    pulseAnimationFrame = _requestPulseFrame(frame);
  }
  function _stopPulseAnimation() {
    _cancelPulseFrame(pulseAnimationFrame);
    pulseAnimationFrame = null;
    lastPulseRenderAt = null;
  }
  function _applyPulseStrip(strip, runs) {
    const data = _pulseStripData(runs);
    latestPulseData = data;
    strip.classList.toggle("status-monitor-pulse-active", data.activeCount > 0);
    strip.dataset.pulseSignature = data.signature;
    strip.dataset.pulseCpuSamples = data.cpuSamples.map((value) => Math.round(value).toString()).join(",");
    _applyPulseLoadStyle(strip, data);
    _ensurePulseState(strip, data);
    _renderPulseState(strip, _pulseNow());
  }
  function _renderPulseStrip(runs) {
    const data = _pulseStripData(runs);
    latestPulseData = data;
    const strip = document.createElement("section");
    strip.className = "status-monitor-pulse-strip";
    strip.classList.toggle("status-monitor-pulse-active", data.activeCount > 0);
    strip.dataset.pulseSignature = data.signature;
    strip.dataset.pulseCpuSamples = data.cpuSamples.map((value) => Math.round(value).toString()).join(",");
    strip.dataset.pulseGlowGradientId = `status-monitor-pulse-mobile-glow-${Math.random().toString(36).slice(2)}`;
    _applyPulseLoadStyle(strip, data);
    const sliceAspect = typeof window.matchMedia === "function" && window.matchMedia("(max-width: 600px)").matches;
    const svg = _svgEl("svg", {
      viewBox: "0 0 720 76",
      preserveAspectRatio: sliceAspect ? "xMidYMid slice" : "none",
      class: "status-monitor-pulse-svg",
      "aria-hidden": "true"
    });
    const defs = _svgEl("defs");
    const glowGradient = _svgEl("radialGradient", {
      id: strip.dataset.pulseGlowGradientId,
      cx: "50%",
      cy: "50%",
      r: "50%",
      fx: "50%",
      fy: "50%"
    });
    glowGradient.append(
      _svgEl("stop", { offset: "0%", "stop-color": "var(--green)", "stop-opacity": "1" }),
      _svgEl("stop", { offset: "22%", "stop-color": "var(--green)", "stop-opacity": "0.82" }),
      _svgEl("stop", { offset: "56%", "stop-color": "var(--green)", "stop-opacity": "0.34" }),
      _svgEl("stop", { offset: "84%", "stop-color": "var(--green)", "stop-opacity": "0.08" }),
      _svgEl("stop", { offset: "100%", "stop-color": "var(--green)", "stop-opacity": "0" })
    );
    defs.appendChild(glowGradient);
    const track = _svgEl("g", { class: "status-monitor-pulse-track" });
    track.append(
      _svgEl("g", { class: "status-monitor-pulse-glows" }),
      _svgEl("g", { class: "status-monitor-pulse-beat-glows" }),
      _svgEl("path", { class: "status-monitor-pulse-placeholder-line", d: "" }),
      _svgEl("path", { class: "status-monitor-pulse-line", d: "" })
    );
    svg.append(
      defs,
      _svgEl("path", { class: "status-monitor-pulse-grid", d: "M0 40 L720 40" }),
      track
    );
    strip.append(svg);
    _ensurePulseState(strip, data);
    _renderPulseState(strip, _pulseNow());
    return strip;
  }
  function _constellationPopover() {
    const popover = document.createElement("div");
    popover.className = "status-monitor-constellation-popover";
    popover.setAttribute("aria-hidden", "true");
    const root = document.createElement("div");
    root.className = "status-monitor-constellation-popover-root";
    root.dataset.field = "root";
    const command = document.createElement("div");
    command.className = "status-monitor-constellation-popover-command";
    command.dataset.field = "command";
    const meta = document.createElement("div");
    meta.className = "status-monitor-constellation-popover-meta";
    ["time", "duration", "exit", "lines"].forEach((field) => {
      const item = document.createElement("span");
      item.dataset.field = field;
      meta.appendChild(item);
    });
    popover.append(root, command, meta);
    return popover;
  }
  function _constellationPopoverKey(star) {
    return String(star?.id || star?.command || star?.root || "").trim().toLowerCase();
  }
  function _clearConstellationPopoverTimer(panel) {
    const timer = constellationPopoverTimerByPanel.get(panel);
    if (timer) {
      window.clearTimeout(timer);
      constellationPopoverTimerByPanel.delete(panel);
    }
  }
  function _showConstellationPopover(panel, star, x, y) {
    const popover = panel.querySelector(".status-monitor-constellation-popover");
    if (!popover) return;
    _clearConstellationPopoverTimer(panel);
    panel.dataset.constellationPopoverStar = _constellationPopoverKey(star);
    const plot = popover.parentElement;
    const root = String(star.root || "run");
    const category = String(star.category || "Other");
    const exitCode = _exitCodeLabel(star.exit_code);
    popover.querySelector('[data-field="root"]').textContent = `${root} · ${category}`;
    popover.querySelector('[data-field="command"]').textContent = _truncateText(star.command || root, 92);
    popover.querySelector('[data-field="time"]').textContent = _formatStarStarted(star.started);
    popover.querySelector('[data-field="duration"]').textContent = _formatDurationSeconds(star.elapsed_seconds);
    popover.querySelector('[data-field="exit"]').textContent = exitCode;
    popover.querySelector('[data-field="lines"]').textContent = `${_formatCount(star.output_line_count || 0)} lines`;
    const svg = plot?.querySelector?.(".status-monitor-constellation");
    const target = _plotPixelFromViewBox(svg, Number(x), Number(y), 640, 300);
    const plotWidth = target.plotWidth;
    const plotHeight = target.plotHeight;
    const targetX = target.x;
    const targetY = target.y;
    const popoverRect = popover.getBoundingClientRect?.() || {};
    const fallbackWidth = Math.min(280, Math.max(1, plotWidth - 22));
    const popoverWidth = popover.offsetWidth || Number(popoverRect.width) || fallbackWidth;
    const popoverHeight = popover.offsetHeight || Number(popoverRect.height) || 92;
    const margin = 8;
    const gap = 12;
    const maxLeft = Math.max(margin, plotWidth - popoverWidth - margin);
    const maxTop = Math.max(margin, plotHeight - popoverHeight - margin);
    const below = targetY < popoverHeight + gap + margin;
    const left = _clampNumber(targetX - popoverWidth / 2, margin, maxLeft);
    const preferredTop = below ? targetY + gap : targetY - popoverHeight - gap;
    const top = _clampNumber(preferredTop, margin, maxTop);
    popover.style.left = `${left.toFixed(1)}px`;
    popover.style.top = `${top.toFixed(1)}px`;
    popover.classList.toggle("status-monitor-constellation-popover-below", below);
    popover.classList.add("status-monitor-constellation-popover-visible");
    popover.setAttribute("aria-hidden", "false");
  }
  function _scheduleConstellationPopover(panel, star, x, y) {
    const key = _constellationPopoverKey(star);
    if (panel.dataset.constellationPopoverStar === key) return;
    _clearConstellationPopoverTimer(panel);
    const timer = window.setTimeout(() => {
      constellationPopoverTimerByPanel.delete(panel);
      _showConstellationPopover(panel, star, x, y);
    }, CONSTELLATION_POPOVER_MOVE_DELAY_MS);
    constellationPopoverTimerByPanel.set(panel, timer);
  }
  function _hideConstellationPopover(panel) {
    const popover = panel.querySelector(".status-monitor-constellation-popover");
    if (!popover) return;
    _clearConstellationPopoverTimer(panel);
    delete panel.dataset.constellationPopoverStar;
    popover.classList.remove("status-monitor-constellation-popover-visible", "status-monitor-constellation-popover-below");
    popover.setAttribute("aria-hidden", "true");
  }
  function _constellationSparseMessage(starCount) {
    const count = Number(starCount || 0);
    if (count <= 0) return "Run history will populate this constellation.";
    if (count < 5) return "More runs will sharpen this map.";
    return "";
  }
  function _splitConstellationStreakSegments(group) {
    const TWO_HOURS_MS = 2 * 60 * 60 * 1e3;
    const segments = [];
    let current = [];
    let previous = null;
    for (const point of group) {
      if (previous) {
        const sameDay = new Date(previous.started).toDateString() === new Date(point.started).toDateString();
        const within2h = point.started - previous.started <= TWO_HOURS_MS;
        if (!sameDay || !within2h) {
          if (current.length >= 2) segments.push(current);
          current = [];
        }
      }
      current.push(point);
      previous = point;
    }
    if (current.length >= 2) segments.push(current);
    return segments;
  }
  function _constellationStreakPath(points) {
    if (!Array.isArray(points) || points.length < 2) return "";
    if (points.length === 2) {
      return _pathFromPoints([[points[0].x, points[0].y], [points[1].x, points[1].y]]);
    }
    const commands = [`M${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`];
    for (let index = 1; index < points.length - 1; index += 1) {
      const current = points[index];
      const next = points[index + 1];
      const midX = (current.x + next.x) / 2;
      const midY = (current.y + next.y) / 2;
      commands.push(`Q${current.x.toFixed(1)} ${current.y.toFixed(1)} ${midX.toFixed(1)} ${midY.toFixed(1)}`);
    }
    const last = points[points.length - 1];
    commands.push(`L${last.x.toFixed(1)} ${last.y.toFixed(1)}`);
    return commands.join(" ");
  }
  const CONSTELLATION_TICK_STEP_CANDIDATES = [1, 2, 3, 4, 6, 8, 12];
  function _constellationTickSpec(window2, segments) {
    const startMin = Number(window2?.startMin) || 0;
    const endMin = Number(window2?.endMin) || 1440;
    const spans = Array.isArray(segments) && segments.length ? segments : [{ startMin, endMin }];
    const totalVisibleMin = spans.reduce(
      (sum, s) => sum + Math.max(0, (Number(s.endMin) || 0) - (Number(s.startMin) || 0)),
      0
    );
    const spanH = totalVisibleMin / 60;
    const target = spanH <= 6 ? 4 : spanH <= 12 ? 5 : 6;
    let bestStep = CONSTELLATION_TICK_STEP_CANDIDATES[0];
    let bestScore = Infinity;
    CONSTELLATION_TICK_STEP_CANDIDATES.forEach((step) => {
      let count = 0;
      spans.forEach((s) => {
        const firstHour = Math.ceil((Number(s.startMin) || 0) / 60 / step) * step;
        const endHour = (Number(s.endMin) || 0) / 60;
        for (let hour = firstHour; hour <= endHour + 1e-9; hour += step) count += 1;
      });
      const undershoot = count < target ? (target - count) * 100 : 0;
      const distance = Math.abs(count - target);
      const score = undershoot + distance - step * 1e-3;
      if (score < bestScore) {
        bestScore = score;
        bestStep = step;
      }
    });
    const majors = [];
    const minors = [];
    const half = bestStep / 2;
    spans.forEach((s) => {
      const segStartMin = Number(s.startMin) || 0;
      const segEndMin = Number(s.endMin) || 0;
      const segStartH = segStartMin / 60;
      const segEndH = segEndMin / 60;
      const firstHour = Math.ceil(segStartH / bestStep) * bestStep;
      const segMajors = [];
      for (let hour = firstHour; hour <= segEndH + 1e-9; hour += bestStep) {
        segMajors.push(hour);
        majors.push(hour);
      }
      if (half > 0) {
        segMajors.forEach((hour, index) => {
          const next = segMajors[index + 1];
          if (typeof next === "number" && next - hour > half * 1.5) return;
          const candidate = hour + half;
          if (candidate > segStartH + 1e-9 && candidate < segEndH - 1e-9) {
            minors.push(candidate);
          }
        });
        const leading = firstHour - half;
        if (leading > segStartH + 1e-9 && leading < segEndH - 1e-9) minors.push(leading);
      }
    });
    return { stepHours: bestStep, majors, minors };
  }
  function _formatConstellationSpanLabel(span) {
    const pad = (value) => String(Math.floor(value)).padStart(2, "0");
    const startMin = Math.max(0, Math.min(1440, Number(span?.startMin) || 0));
    const endMin = Math.max(0, Math.min(1440, Number(span?.endMin) || 1440));
    return `${pad(startMin / 60)}:${pad(startMin % 60)}–${pad(endMin / 60)}:${pad(endMin % 60)}`;
  }
  function _formatConstellationWindowLabel(window2, segments) {
    if (Array.isArray(segments) && segments.length > 1) {
      return segments.map(_formatConstellationSpanLabel).join(", ");
    }
    return _formatConstellationSpanLabel(window2);
  }
  function _isConstellationFullDay() {
    const readPreference = typeof getConstellationFullDayPreference !== "undefined" && getConstellationFullDayPreference || _statusMonitorGlobalFunction("getConstellationFullDayPreference");
    return typeof readPreference === "function" && readPreference() === "on";
  }
  const CONSTELLATION_SKY_GRADIENT_ID = "constellation-sky";
  const CONSTELLATION_SKY_STOPS = [
    { hour: 0, bg: 28, shadow: 72 },
    { hour: 5, bg: 28, shadow: 72 },
    { hour: 7, bg: 44, shadow: 56 },
    { hour: 8, bg: 62, shadow: 38 },
    { hour: 17, bg: 62, shadow: 38 },
    { hour: 19, bg: 44, shadow: 56 },
    { hour: 20, bg: 32, shadow: 68 },
    { hour: 24, bg: 28, shadow: 72 }
  ];
  const CONSTELLATION_SKY_TOP = 12;
  const CONSTELLATION_SKY_BOTTOM = 286;
  function _appendConstellationSkyBackdrop(svg, window2, segments) {
    const minuteToX = _constellationMinuteToX(window2, segments);
    const x = minuteToX(0);
    const width = minuteToX(1440) - x;
    const defs = _svgEl("defs");
    const gradient = _svgEl("linearGradient", {
      id: CONSTELLATION_SKY_GRADIENT_ID,
      x1: "0%",
      y1: "0%",
      x2: "100%",
      y2: "0%"
    });
    const span = Math.max(1, width);
    CONSTELLATION_SKY_STOPS.forEach(({ hour, bg, shadow }) => {
      const stopX = minuteToX(hour * 60);
      const offsetPercent = Math.max(0, Math.min(100, (stopX - x) / span * 100));
      gradient.appendChild(_svgEl("stop", {
        offset: `${offsetPercent}%`,
        "stop-color": `color-mix(in srgb, var(--theme-panel-bg) ${bg}%, var(--theme-panel-shadow) ${shadow}%)`
      }));
    });
    defs.appendChild(gradient);
    svg.appendChild(defs);
    svg.appendChild(_svgEl("rect", {
      class: "status-monitor-constellation-sky",
      x,
      y: CONSTELLATION_SKY_TOP,
      width,
      height: CONSTELLATION_SKY_BOTTOM - CONSTELLATION_SKY_TOP,
      fill: `url(#${CONSTELLATION_SKY_GRADIENT_ID})`
    }));
  }
  function _appendConstellationSeamMarkers(svg, window2, segments) {
    if (!Array.isArray(segments) || segments.length < 2) return;
    const minuteToX = _constellationMinuteToX(window2, segments);
    for (let i = 0; i < segments.length - 1; i += 1) {
      const seamX = minuteToX(segments[i].endMin);
      svg.appendChild(_svgEl("line", {
        class: "status-monitor-constellation-seam",
        x1: seamX,
        y1: CONSTELLATION_SKY_TOP,
        x2: seamX,
        y2: CONSTELLATION_SKY_BOTTOM
      }));
      const label = _svgEl("text", {
        class: "status-monitor-constellation-seam-label",
        x: seamX,
        y: 289,
        "text-anchor": "middle"
      });
      label.textContent = "//";
      svg.appendChild(label);
    }
  }
  function _rerenderConstellationPanelInPlace() {
    const existing = document.querySelector(".status-monitor-constellation-card");
    if (!existing) return;
    const fresh = _renderConstellationPanel();
    existing.replaceWith(fresh);
  }
  function _constellationMetaText(stars, fullDay, window2, segments) {
    const count = Array.isArray(stars) ? stars.length : 0;
    const windowLabel = _insightWindowLabel("constellation", 30);
    if (!count) return `awaiting run history · ${windowLabel}`;
    const hasDeadBands = Array.isArray(segments) && segments.length > 1;
    const isFullDayWindow = Number(window2?.startMin) <= 0 && Number(window2?.endMin) >= 1440;
    if ((fullDay || isFullDayWindow) && !hasDeadBands) {
      return `${_formatCount(count)} plotted · ${windowLabel}`;
    }
    return `${_formatConstellationWindowLabel(window2, segments)} · ${_formatCount(count)} plotted`;
  }
  function _toggleConstellationFullDay() {
    const next = _isConstellationFullDay() ? "off" : "on";
    const applyPreference = typeof applyConstellationFullDayPreference !== "undefined" && applyConstellationFullDayPreference || _statusMonitorGlobalFunction("applyConstellationFullDayPreference");
    if (typeof applyPreference === "function") applyPreference(next, true);
    _rerenderConstellationPanelInPlace();
  }
  function _buildConstellationFullDayToggle(fullDay) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "toggle-btn status-monitor-constellation-toggle";
    btn.setAttribute("aria-pressed", fullDay ? "true" : "false");
    btn.title = fullDay ? "Switch to active-hours layout" : "Switch to full-day layout";
    btn.setAttribute("aria-label", fullDay ? "Constellation showing full 24-hour day. Activate to switch to active-hours layout." : "Constellation showing active hours. Activate to switch to full 24-hour layout.");
    btn.textContent = fullDay ? "Full day" : "Active hours";
    if (typeof bindPressableFn === "function") {
      bindPressableFn(btn, {
        onActivate: _toggleConstellationFullDay,
        refocusComposer: false
      });
    } else {
      btn.addEventListener("click", _toggleConstellationFullDay);
    }
    return btn;
  }
  function _formatConstellationAxisDuration(seconds) {
    const total = Math.max(0, Number(seconds) || 0);
    if (total < 1) return "0s";
    if (total < 60) return `${Math.round(total)}s`;
    if (total < 3600) return `${Math.round(total / 60)}m`;
    const hours = total / 3600;
    if (hours >= 10) return `${Math.round(hours)}h`;
    if (Math.abs(hours - Math.round(hours)) < 0.05) return `${Math.round(hours)}h`;
    return `${hours.toFixed(1)}h`;
  }
  function _appendConstellationElapsedGuides(svg, ceilingElapsed) {
    const ceiling = Number.isFinite(ceilingElapsed) && ceilingElapsed > 0 ? ceilingElapsed : 1;
    const logCeil = Math.log1p(ceiling);
    const ticks = [
      { fraction: 0, major: true },
      { fraction: 0.25, major: false },
      { fraction: 0.5, major: true },
      { fraction: 0.75, major: false },
      { fraction: 1, major: true }
    ];
    for (const { fraction, major } of ticks) {
      const y = CONSTELLATION_Y_BASELINE - fraction * CONSTELLATION_Y_RANGE;
      svg.appendChild(_svgEl("line", {
        class: major ? "status-monitor-constellation-guide status-monitor-constellation-guide-major" : "status-monitor-constellation-guide status-monitor-constellation-guide-minor",
        x1: CONSTELLATION_PLOT_LEFT,
        y1: y,
        x2: CONSTELLATION_PLOT_RIGHT,
        y2: y
      }));
      const seconds = Math.expm1(fraction * logCeil);
      const label = _svgEl("text", {
        class: "status-monitor-constellation-guide-label status-monitor-constellation-guide-label-y",
        x: CONSTELLATION_PLOT_LEFT - 6,
        y,
        "text-anchor": "end"
      });
      label.textContent = _formatConstellationAxisDuration(seconds);
      svg.appendChild(label);
    }
  }
  function _appendConstellationTimeGuides(svg, window2 = CONSTELLATION_FULL_DAY_WINDOW, segments) {
    const { majors, minors } = _constellationTickSpec(window2, segments);
    const minuteToX = _constellationMinuteToX(window2, segments);
    const endMin = Number(window2?.endMin) || 1440;
    const endHour = endMin / 60;
    const segmentSpans = Array.isArray(segments) && segments.length > 1 ? segments : null;
    const hourIsVisible = (hour) => {
      if (!segmentSpans) return true;
      const minute = hour * 60;
      return segmentSpans.some((s) => minute > s.startMin + 1e-6 && minute < s.endMin - 1e-6);
    };
    minors.forEach((hour) => {
      if (!hourIsVisible(hour)) return;
      const x = minuteToX(hour * 60);
      svg.appendChild(_svgEl("line", {
        class: "status-monitor-constellation-guide status-monitor-constellation-guide-minor",
        x1: x,
        y1: 12,
        x2: x,
        y2: 286
      }));
    });
    majors.forEach((hour) => {
      const x = minuteToX(hour * 60);
      svg.appendChild(_svgEl("line", {
        class: "status-monitor-constellation-guide status-monitor-constellation-guide-major",
        x1: x,
        y1: 12,
        x2: x,
        y2: 286
      }));
      if (hour >= endHour - 1e-6) return;
      if (!hourIsVisible(hour)) return;
      const displayHour = (Math.round(hour) % 24 + 24) % 24;
      const label = _svgEl("text", {
        class: "status-monitor-constellation-guide-label",
        x: Math.max(CONSTELLATION_PLOT_LEFT, Math.min(CONSTELLATION_PLOT_RIGHT + 4, x)),
        y: 289,
        "text-anchor": "middle"
      });
      label.textContent = String(displayHour).padStart(2, "0");
      svg.appendChild(label);
    });
  }
  function _syncConstellationAspect(svg) {
    const rect = svg?.getBoundingClientRect?.();
    const width = Number(rect?.width || 0);
    const height = Number(rect?.height || 0);
    if (width <= 0 || height <= 0) return;
    const xScale = width / 640;
    const yScale = height / 300;
    const starScaleX = xScale > 0 && yScale > 0 ? _clampNumber(yScale / xScale, 0.34, 1.4) : 1;
    svg.style.setProperty("--constellation-star-scale-x", starScaleX.toFixed(3));
  }
  function _scheduleConstellationAspectSync(svg) {
    _syncConstellationAspect(svg);
    if (typeof window.requestAnimationFrame === "function") {
      window.requestAnimationFrame(() => _syncConstellationAspect(svg));
    }
  }
  function _computeConstellationCeiling(elapsedValues) {
    const finite = [];
    for (const value of elapsedValues) {
      const n = Number(value);
      if (Number.isFinite(n) && n >= 0) finite.push(n);
    }
    if (!finite.length) return 1;
    finite.sort((left, right) => left - right);
    const fullMax = finite[finite.length - 1];
    if (fullMax <= 0) return 1;
    const p98Index = Math.max(0, Math.ceil(finite.length * 0.98) - 1);
    const p98 = finite[p98Index];
    const padded = p98 * 1.06;
    const step = Math.max(fullMax / 10, 1e-6);
    const quantised = Math.ceil(padded / step) * step;
    const sparsityFloor = fullMax * 0.25;
    return Math.max(sparsityFloor, quantised, 1);
  }
  function _renderConstellationPanel() {
    const insights = cachedInsights || {};
    const stars = Array.isArray(insights.constellation) ? insights.constellation : [];
    const panel = document.createElement("section");
    panel.className = "status-monitor-visual-card status-monitor-constellation-card";
    const fullDayConstellation = _isConstellationFullDay();
    const constellationWindow = fullDayConstellation ? CONSTELLATION_FULL_DAY_WINDOW : _constellationActiveWindow(stars);
    const constellationDeadBands = fullDayConstellation ? [] : _constellationDeadBands(stars);
    const constellationSegments = _constellationVisibleSegments(constellationWindow, constellationDeadBands);
    const constellationHasDeadBands = constellationSegments.length > 1;
    const header = document.createElement("div");
    header.className = "status-monitor-visual-header";
    const title = document.createElement("div");
    title.className = "status-monitor-visual-title";
    title.textContent = "Command Constellation";
    const meta = document.createElement("div");
    meta.className = "status-monitor-visual-meta";
    meta.textContent = _constellationMetaText(stars, fullDayConstellation, constellationWindow, constellationSegments);
    const legend = _categoryLegend(stars);
    if (legend && stars.length) {
      const hasFailed = stars.some((star) => _isFailedExitCode(star?.exit_code));
      if (hasFailed) {
        legend.appendChild(_buildConstellationLegendKey({
          modifier: "failed",
          ariaLabel: "Failed runs are ringed in red",
          label: "Failed"
        }));
      }
      legend.appendChild(_buildConstellationLegendKey({
        modifier: "size",
        ariaLabel: "Star size encodes output line count",
        label: "Output"
      }));
    }
    const fullDayToggle = _buildConstellationFullDayToggle(fullDayConstellation);
    if (legend) {
      legend.appendChild(fullDayToggle);
    }
    header.append(title);
    if (legend) header.appendChild(legend);
    else header.appendChild(fullDayToggle);
    header.appendChild(meta);
    const plot = document.createElement("div");
    plot.className = "status-monitor-constellation-plot";
    plot.addEventListener("pointerleave", () => _hideConstellationPopover(panel));
    plot.addEventListener("focusout", (event) => {
      if (!plot.contains(event.relatedTarget)) _hideConstellationPopover(panel);
    });
    const svg = _svgEl("svg", {
      class: "status-monitor-constellation",
      viewBox: "0 0 640 300",
      role: "img",
      "aria-label": "Recent command constellation",
      preserveAspectRatio: "none"
    });
    const starsByNodeId = /* @__PURE__ */ new Map();
    const starPayloadFromEvent = (event) => {
      const target = event.target;
      const node = target && typeof target.closest === "function" ? target.closest(".status-monitor-star-node") : null;
      if (!node || !svg.contains(node)) return null;
      return starsByNodeId.get(node.dataset.starId || "");
    };
    svg.addEventListener("pointerover", (event) => {
      const payload = starPayloadFromEvent(event);
      if (payload) _showConstellationPopover(panel, payload.star, payload.x, payload.y);
    });
    svg.addEventListener("pointermove", (event) => {
      const payload = starPayloadFromEvent(event);
      if (payload) _scheduleConstellationPopover(panel, payload.star, payload.x, payload.y);
    });
    svg.addEventListener("focusin", (event) => {
      const payload = starPayloadFromEvent(event);
      if (payload) _showConstellationPopover(panel, payload.star, payload.x, payload.y);
    });
    svg.addEventListener("click", (event) => {
      const payload = starPayloadFromEvent(event);
      if (!payload) return;
      event.preventDefault();
      event.stopPropagation();
      _clearDocumentSelection();
      _restoreConstellationRun(payload.star);
    });
    svg.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const payload = starPayloadFromEvent(event);
      if (!payload) return;
      event.preventDefault();
      event.stopPropagation();
      _clearDocumentSelection();
      _restoreConstellationRun(payload.star);
    });
    const ceilingElapsed = _computeConstellationCeiling(
      stars.map((star) => star.elapsed_seconds)
    );
    const constellationMinuteToX = _constellationMinuteToX(constellationWindow, constellationSegments);
    _appendConstellationSkyBackdrop(svg, constellationWindow, constellationSegments);
    _appendConstellationTimeGuides(svg, constellationWindow, constellationSegments);
    _appendConstellationElapsedGuides(svg, ceilingElapsed);
    _ambientConstellationStars({ stars, window: constellationWindow, segments: constellationSegments }).forEach((star) => {
      svg.appendChild(_svgEl("circle", {
        class: "status-monitor-star-ambient",
        cx: star.x,
        cy: star.y,
        r: star.radius,
        style: [
          `--ambient-hue:${star.hue.toFixed(1)}`,
          `--ambient-saturation:${star.saturation.toFixed(1)}%`,
          `--ambient-lightness:${star.lightness.toFixed(1)}%`,
          `--ambient-opacity:${star.opacity.toFixed(2)}`
        ].join(";")
      }));
    });
    const now = Date.now();
    const visibleStars = constellationHasDeadBands ? stars.filter((star) => {
      const minute = _constellationStarMinutes(star);
      if (minute === null) return true;
      return constellationSegments.some((s) => minute >= s.startMin && minute <= s.endMin);
    }) : stars;
    const plottedStars = visibleStars.map((star) => {
      const started = Date.parse(String(star.started || "")) || now;
      const date = new Date(started);
      const minutes = date.getHours() * 60 + date.getMinutes();
      const jitter = _normalizedHash(star.id || star.command || star.root);
      const x = constellationMinuteToX(minutes) + (jitter % 29 - 14) * 0.45;
      const elapsed = Number(star.elapsed_seconds || 0);
      const offScale = elapsed > ceilingElapsed;
      const yBase = CONSTELLATION_Y_BASELINE - Math.log1p(elapsed) / Math.log1p(ceilingElapsed) * CONSTELLATION_Y_RANGE;
      const y = Math.max(18, Math.min(280, yBase + (jitter / 31 % 31 - 15) * 0.65));
      const ageDays = Math.max(0, (now - started) / 864e5);
      const opacity = Math.max(0.28, 1 - ageDays / 34);
      const ageGlow = 0.24 + opacity * 0.56;
      const findingCount = Number(star.finding_count || 0);
      const radiusSource = Math.max(Number(star.output_line_count || 0), findingCount * 40);
      const radius = Math.max(1.8, Math.min(8.5, 2 + Math.sqrt(radiusSource + 1) * 0.18));
      const maxKind = String(star.max_kind || "info");
      const tone = _categoryTone(star.category);
      const starStyle = _constellationToneStyle(tone, { "--star-age-glow": ageGlow.toFixed(2) });
      const failed = _isFailedExitCode(star.exit_code);
      return {
        star,
        started,
        x,
        y,
        radius,
        opacity,
        tone,
        maxKind,
        findingCount,
        starStyle,
        failed,
        offScale
      };
    });
    const streakGroups = /* @__PURE__ */ new Map();
    plottedStars.forEach((point) => {
      const key = String(point.star?.root || "").trim().toLowerCase();
      if (!key) return;
      const group = streakGroups.get(key) || [];
      group.push(point);
      streakGroups.set(key, group);
    });
    streakGroups.forEach((group) => {
      if (group.length < 2) return;
      group.sort((left, right) => left.started - right.started);
      const tone = group[0].tone;
      const segments = _splitConstellationStreakSegments(group);
      segments.forEach((segment) => {
        const path = _constellationStreakPath(segment);
        if (!path) return;
        const kindClass = _constellationKindClass(segment[0].maxKind, "status-monitor-constellation-streak");
        svg.appendChild(_svgEl("path", {
          class: [
            "status-monitor-constellation-streak",
            kindClass
          ].filter(Boolean).join(" "),
          d: path,
          style: _constellationToneStyle(tone)
        }));
      });
    });
    plottedStars.forEach(({ star, x, y, radius, opacity, starStyle, failed, offScale, maxKind, findingCount }, index) => {
      const starId = String(star.id || `${star.root || "run"}:${star.started || ""}:${index}`);
      starsByNodeId.set(starId, { star, x, y });
      const nodeKindClass = _constellationKindClass(maxKind, "status-monitor-star-node");
      const node = _svgEl("g", {
        class: [
          "status-monitor-star-node",
          offScale ? "status-monitor-star-node-offscale" : "",
          nodeKindClass
        ].filter(Boolean).join(" "),
        tabindex: "0",
        role: "button",
        "aria-label": `${star.root || "run"} ${_formatStarStarted(star.started)}${findingCount ? `, ${findingCount} findings` : ""}`,
        "data-star-id": starId,
        "data-run-id": star.id || ""
      });
      const ring = _svgEl("circle", {
        class: "status-monitor-star-ring",
        cx: x,
        cy: y,
        r: radius + 4.5,
        style: starStyle
      });
      const failureRing = failed ? _svgEl("circle", {
        class: "status-monitor-star-failure-ring",
        cx: x,
        cy: y,
        r: radius + 2.2,
        opacity
      }) : null;
      const circle = _svgEl("circle", {
        class: [
          "status-monitor-star",
          failed ? "status-monitor-star-failed" : "",
          maxKind === "error" ? "status-monitor-star-kind-error" : "",
          maxKind === "warn" ? "status-monitor-star-kind-warn" : ""
        ].filter(Boolean).join(" "),
        cx: x,
        cy: y,
        r: radius,
        opacity,
        style: starStyle
      });
      const hit = _svgEl("circle", {
        class: "status-monitor-star-hit",
        cx: x,
        cy: y,
        r: Math.max(12, radius + 9)
      });
      node.append(ring);
      if (failureRing) node.appendChild(failureRing);
      if (offScale) {
        const tickTop = Math.max(4, y - radius - 7);
        const tickBottom = Math.max(tickTop + 1, y - radius - 1.5);
        node.appendChild(_svgEl("line", {
          class: "status-monitor-star-offscale-tick",
          x1: x,
          x2: x,
          y1: tickTop,
          y2: tickBottom,
          style: starStyle
        }));
      }
      node.append(circle, hit);
      svg.appendChild(node);
    });
    _appendConstellationSeamMarkers(svg, constellationWindow, constellationSegments);
    plot.append(svg, _constellationPopover());
    const sparseMessage = _constellationSparseMessage(stars.length);
    if (sparseMessage) {
      const sparse = document.createElement("div");
      sparse.className = "status-monitor-constellation-sparse";
      sparse.textContent = sparseMessage;
      plot.appendChild(sparse);
    }
    panel.append(header, plot);
    _scheduleConstellationAspectSync(svg);
    return panel;
  }
  function _treemapWorstAspect(row, sideLength) {
    if (!row.length || sideLength <= 0) return Infinity;
    const areas = row.map((entry) => entry.area).filter((area) => area > 0);
    if (!areas.length) return Infinity;
    const sum = areas.reduce((total, area) => total + area, 0);
    const min = Math.min(...areas);
    const max = Math.max(...areas);
    const sideSquared = sideLength * sideLength;
    return Math.max(sideSquared * max / (sum * sum), sum * sum / (sideSquared * min));
  }
  function _treemapLayoutRow(row, box, rects) {
    const rowArea = row.reduce((sum, entry) => sum + entry.area, 0);
    if (!row.length || rowArea <= 0 || box.width <= 0 || box.height <= 0) return box;
    if (box.width >= box.height) {
      const columnWidth = rowArea / box.height;
      let cursorY = box.y;
      row.forEach((entry, index) => {
        const rectHeight = index === row.length - 1 ? box.y + box.height - cursorY : entry.area / columnWidth;
        rects.push({ item: entry.item, x: box.x, y: cursorY, width: columnWidth, height: rectHeight });
        cursorY += rectHeight;
      });
      return { x: box.x + columnWidth, y: box.y, width: Math.max(0, box.width - columnWidth), height: box.height };
    }
    const rowHeight = rowArea / box.width;
    let cursorX = box.x;
    row.forEach((entry, index) => {
      const rectWidth = index === row.length - 1 ? box.x + box.width - cursorX : entry.area / rowHeight;
      rects.push({ item: entry.item, x: cursorX, y: box.y, width: rectWidth, height: rowHeight });
      cursorX += rectWidth;
    });
    return { x: box.x, y: box.y + rowHeight, width: box.width, height: Math.max(0, box.height - rowHeight) };
  }
  function _treemapLayout(items, x, y, width, height) {
    if (!items.length || width <= 0 || height <= 0) return [];
    const entries = items.map((item) => ({ item, value: Math.max(1, Number(item.count || 0)) })).sort((left, right) => right.value - left.value);
    const total = entries.reduce((sum, entry) => sum + entry.value, 0);
    const totalArea = width * height;
    const pending = entries.map((entry) => ({
      item: entry.item,
      area: entry.value / total * totalArea
    }));
    const rects = [];
    let box = { x, y, width, height };
    let row = [];
    while (pending.length) {
      const entry = pending[0];
      const side = Math.min(box.width, box.height);
      const currentWorst = _treemapWorstAspect(row, side);
      const nextWorst = _treemapWorstAspect([...row, entry], side);
      if (!row.length || nextWorst <= currentWorst) {
        row.push(entry);
        pending.shift();
      } else {
        box = _treemapLayoutRow(row, box, rects);
        row = [];
      }
    }
    if (row.length) _treemapLayoutRow(row, box, rects);
    return rects;
  }
  function _treemapFailureRate(item) {
    const succeeded = Math.max(0, Number(item?.succeeded || 0));
    const failed = Math.max(0, Number(item?.failed || 0));
    const incomplete = Math.max(0, Number(item?.incomplete || 0));
    const total = succeeded + failed + incomplete;
    return total > 0 ? failed / total : 0;
  }
  function _showTreemapPopover(panel, item, tile, event = null) {
    const popover = panel.querySelector(".status-monitor-constellation-popover");
    if (!popover || !tile) return;
    const plot = popover.parentElement;
    const succeeded = Math.max(0, Number(item?.succeeded || 0));
    const failed = Math.max(0, Number(item?.failed || 0));
    const incomplete = Math.max(0, Number(item?.incomplete || 0));
    const total = succeeded + failed + incomplete;
    const failureRate = _treemapFailureRate(item) * 100;
    const category = String(item?.category || "Other");
    popover.querySelector('[data-field="root"]').textContent = `${item?.root || "command"} · ${category}`;
    popover.querySelector('[data-field="command"]').textContent = `${_formatCount(item?.count || 0)} ${Number(item?.count || 0) === 1 ? "run" : "runs"} mapped`;
    popover.querySelector('[data-field="time"]').textContent = `${_formatCount(succeeded)} success`;
    popover.querySelector('[data-field="duration"]').textContent = `${_formatCount(failed)} fail`;
    popover.querySelector('[data-field="exit"]').textContent = `${_formatCount(incomplete)} incomplete`;
    popover.querySelector('[data-field="lines"]').textContent = total ? `${_formatPercent(failureRate)} fail rate` : "no outcomes";
    const plotRect = plot?.getBoundingClientRect?.() || {};
    const tileRect = tile.getBoundingClientRect?.() || {};
    const plotWidth = Number(plotRect.width) || 280;
    const plotHeight = Number(plotRect.height) || 140;
    const hasPointer = event && Number.isFinite(Number(event.clientX)) && Number.isFinite(Number(event.clientY));
    const targetX = hasPointer ? Number(event.clientX) - Number(plotRect.left || 0) : Number(tileRect.left) - Number(plotRect.left || 0) + Number(tileRect.width) / 2;
    const targetY = hasPointer ? Number(event.clientY) - Number(plotRect.top || 0) : Number(tileRect.top) - Number(plotRect.top || 0) + Number(tileRect.height) / 2;
    const popoverRect = popover.getBoundingClientRect?.() || {};
    const fallbackWidth = Math.min(240, Math.max(1, plotWidth - 22));
    const popoverWidth = popover.offsetWidth || Number(popoverRect.width) || fallbackWidth;
    const popoverHeight = popover.offsetHeight || Number(popoverRect.height) || 92;
    const margin = 8;
    const gap = 14;
    const maxLeft = Math.max(margin, plotWidth - popoverWidth - margin);
    const maxTop = Math.max(margin, plotHeight - popoverHeight - margin);
    const roomRight = plotWidth - targetX - margin;
    const placeLeft = roomRight < popoverWidth + gap && targetX > popoverWidth + gap + margin;
    const preferredLeft = placeLeft ? targetX - popoverWidth - gap : targetX + gap;
    const left = _clampNumber(preferredLeft, margin, maxLeft);
    const top = _clampNumber(targetY - popoverHeight / 2, margin, maxTop);
    popover.style.left = `${left.toFixed(1)}px`;
    popover.style.top = `${top.toFixed(1)}px`;
    popover.classList.toggle("status-monitor-constellation-popover-below", false);
    popover.classList.add("status-monitor-constellation-popover-visible");
    popover.setAttribute("aria-hidden", "false");
  }
  function _renderTreemapPanel() {
    const insights = cachedInsights || {};
    const items = (Array.isArray(insights.command_mix) ? insights.command_mix : []).slice(0, 14);
    const panel = document.createElement("section");
    panel.className = "status-monitor-visual-card status-monitor-treemap-card";
    const header = document.createElement("div");
    header.className = "status-monitor-visual-header";
    const title = document.createElement("div");
    title.className = "status-monitor-visual-title";
    title.textContent = "Command Territory";
    const meta = document.createElement("div");
    meta.className = "status-monitor-visual-meta";
    meta.textContent = items.length ? `${_formatCount(items.reduce((sum, item) => sum + Number(item.count || 0), 0))} runs · ${_insightWindowLabel("command_mix", 30)}` : `no commands yet · ${_insightWindowLabel("command_mix", 30)}`;
    const legend = _categoryLegend(items);
    header.append(title);
    if (legend) header.appendChild(legend);
    header.appendChild(meta);
    const map = document.createElement("div");
    map.className = "status-monitor-treemap";
    map.addEventListener("pointerleave", () => _hideConstellationPopover(panel));
    map.addEventListener("focusout", (event) => {
      if (!map.contains(event.relatedTarget)) _hideConstellationPopover(panel);
    });
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "status-monitor-visual-empty";
      empty.textContent = "Run history will draw command territory here.";
      map.appendChild(empty);
    } else {
      _treemapLayout(items, 0, 0, 100, 100).forEach(({ item, x, y, width, height }) => {
        const tile = document.createElement("div");
        const tone = _categoryTone(item.category);
        const highlightKey = String(item.root || item.category || "").trim().toLowerCase();
        const highlightSeed = _normalizedHash(highlightKey);
        tile.className = "status-monitor-treemap-tile";
        const tileArea = width * height;
        const stacksDetail = height >= 30 && tileArea >= 220;
        const inlinesDetail = !stacksDetail && width >= 18 && height >= 12 && tileArea >= 120;
        if (!stacksDetail) {
          tile.classList.add("status-monitor-treemap-tile-compact");
        }
        if (inlinesDetail) {
          tile.classList.add("status-monitor-treemap-tile-inline");
        } else if (!stacksDetail) {
          tile.classList.add("status-monitor-treemap-tile-tiny");
        }
        tile.tabIndex = 0;
        tile.setAttribute("role", "button");
        tile.style.left = `${x}%`;
        tile.style.top = `${y}%`;
        tile.style.width = `${width}%`;
        tile.style.height = `${height}%`;
        tile.style.setProperty("--category-hue", String(tone.hue));
        tile.style.setProperty("--category-saturation", `${tone.saturation}%`);
        if (tone.saturation === 0) {
          tile.style.setProperty("--category-saturation-strong", "0%");
          tile.style.setProperty("--category-saturation-mid", "0%");
          tile.style.setProperty("--category-saturation-low", "0%");
        }
        tile.style.setProperty("--tile-glow-x", `${14 + highlightSeed % 52}%`);
        tile.style.setProperty("--tile-glow-y", `${14 + _normalizedHash(`${highlightKey}:y`) % 44}%`);
        const failureRate = _treemapFailureRate(item);
        tile.style.setProperty("--failure-alpha", failureRate ? (0.26 + failureRate * 0.46).toFixed(2) : "0");
        tile.style.setProperty("--failure-stop", `${Math.max(0, failureRate * 100 - 8).toFixed(1)}%`);
        tile.style.setProperty("--failure-fade", `${Math.min(100, failureRate * 100 + 22).toFixed(1)}%`);
        tile.setAttribute("aria-label", `${item.root}: ${item.count} run(s), ${item.category}`);
        tile.addEventListener("pointermove", (event) => _showTreemapPopover(panel, item, tile, event));
        tile.addEventListener("focus", () => _showTreemapPopover(panel, item, tile));
        tile.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          _clearDocumentSelection();
          _openHistoryForCommandRoot(item.root);
        });
        tile.addEventListener("keydown", (event) => {
          if (event.key !== "Enter" && event.key !== " ") return;
          event.preventDefault();
          event.stopPropagation();
          _clearDocumentSelection();
          _openHistoryForCommandRoot(item.root);
        });
        const root = document.createElement("div");
        root.className = "status-monitor-treemap-root";
        root.textContent = item.root;
        const details = document.createElement("div");
        details.className = "status-monitor-treemap-detail";
        const count = Number(item.count || 0);
        const completed = Number(item.succeeded || 0) + Number(item.failed || 0);
        const successRate = completed ? Number(item.succeeded || 0) / completed * 100 : null;
        details.textContent = count < 5 ? `${_formatCount(item.count)} ${count === 1 ? "run" : "runs"}` : `${_formatCount(item.count)} · ${successRate === null ? "n/a" : _formatPercent(successRate)}`;
        tile.append(root, details);
        map.appendChild(tile);
      });
    }
    const popover = _constellationPopover();
    popover.classList.add("status-monitor-treemap-popover");
    map.appendChild(popover);
    panel.append(header, map);
    return panel;
  }
  function _renderHeatmapPanel() {
    const insights = cachedInsights || {};
    const days = Array.isArray(insights.activity) ? insights.activity : [];
    const maxCount = Math.max(1, Number(insights.max_day_count || 0));
    const panel = document.createElement("section");
    panel.className = "status-monitor-visual-card status-monitor-heatmap-card";
    const header = document.createElement("div");
    header.className = "status-monitor-visual-header";
    const title = document.createElement("div");
    title.className = "status-monitor-visual-title";
    title.textContent = "Activity Heatmap";
    const meta = document.createElement("div");
    meta.className = "status-monitor-visual-meta";
    meta.textContent = `${_formatCount(days.reduce((sum, day) => sum + Number(day.count || 0), 0))} runs / ${_insightWindowLabel("activity", Number(insights.days || days.length || 28))}`;
    const legend = document.createElement("div");
    legend.className = "status-monitor-heatmap-legend";
    const less = document.createElement("span");
    less.textContent = "Less";
    legend.appendChild(less);
    for (let level = 0; level <= 4; level += 1) {
      const swatch = document.createElement("span");
      swatch.className = `status-monitor-heatmap-legend-swatch status-monitor-heatmap-level-${level}`;
      swatch.setAttribute("aria-hidden", "true");
      legend.appendChild(swatch);
    }
    const more = document.createElement("span");
    more.textContent = "More";
    legend.appendChild(more);
    const metaGroup = document.createElement("div");
    metaGroup.className = "status-monitor-heatmap-meta-group";
    metaGroup.append(meta, legend);
    header.append(title, metaGroup);
    const calendar = _heatmapCalendarDays(days, insights.first_run_date);
    const body = document.createElement("div");
    body.className = "status-monitor-heatmap-body";
    if (calendar.weekCount) {
      body.style.setProperty("--status-heatmap-weeks", String(calendar.weekCount));
    }
    const months = document.createElement("div");
    months.className = "status-monitor-heatmap-months";
    _heatmapMonthMarkers(calendar).forEach((marker) => {
      const label = document.createElement("span");
      label.className = "status-monitor-heatmap-month";
      label.textContent = marker.label;
      label.style.gridColumn = `${marker.column}`;
      months.appendChild(label);
    });
    const weekdays = document.createElement("div");
    weekdays.className = "status-monitor-heatmap-weekdays";
    [
      ["Mon", 1],
      ["Wed", 3],
      ["Fri", 5]
    ].forEach(([labelText, row]) => {
      const label = document.createElement("span");
      label.className = "status-monitor-heatmap-weekday";
      label.textContent = labelText;
      label.style.gridRow = `${row}`;
      weekdays.appendChild(label);
    });
    const grid = document.createElement("div");
    grid.className = "status-monitor-heatmap";
    const heatmapDaysByCell = /* @__PURE__ */ new WeakMap();
    calendar.cells.forEach((day) => {
      const cell = document.createElement("span");
      const count = Number(day.count || 0);
      const level = count <= 0 ? 0 : Math.max(1, Math.min(4, Math.ceil(count / maxCount * 4)));
      cell.className = [
        "status-monitor-heatmap-cell",
        `status-monitor-heatmap-level-${level}`,
        day.outOfRange ? "status-monitor-heatmap-out-of-range" : ""
      ].filter(Boolean).join(" ");
      cell.dataset.date = day.date;
      cell.style.gridColumn = `${day.column}`;
      cell.style.gridRow = `${day.row}`;
      cell.tabIndex = 0;
      cell.setAttribute("aria-label", `${day.date}: ${_formatCount(count)} ${count === 1 ? "run" : "runs"}`);
      heatmapDaysByCell.set(cell, day);
      cell.addEventListener("focus", () => _showHeatmapPopover(panel, day, cell));
      grid.appendChild(cell);
    });
    const handleHeatmapPointer = (event) => {
      const target = event.target;
      const cell = target && typeof target.closest === "function" ? target.closest(".status-monitor-heatmap-cell") : null;
      if (!cell || !body.contains(cell)) return;
      const day = heatmapDaysByCell.get(cell);
      if (day) _showHeatmapPopover(panel, day, cell, event);
    };
    body.addEventListener("pointerover", handleHeatmapPointer);
    body.addEventListener("pointermove", handleHeatmapPointer);
    body.addEventListener("pointerleave", () => _hideConstellationPopover(panel));
    body.addEventListener("focusout", (event) => {
      if (!body.contains(event.relatedTarget)) _hideConstellationPopover(panel);
    });
    const popover = _constellationPopover();
    popover.classList.add("status-monitor-heatmap-popover");
    body.append(months, weekdays, grid, popover);
    panel.append(header, body);
    return panel;
  }
  function _eventTickerEvents() {
    const insights = cachedInsights || {};
    const events = Array.isArray(insights.events) ? insights.events : [];
    return events.length ? events : [{ root: "idle", command: "waiting for run events", exit_code: null }];
  }
  function _eventTickerSignature(events) {
    return events.map((event) => [
      event.root || "",
      event.command || "",
      event.started || "",
      event.finished || "",
      event.exit_code ?? "active",
      event.elapsed_seconds ?? ""
    ].join(":")).join("|");
  }
  function _populateEventTickerRow(row, events) {
    row.replaceChildren();
    [...events, ...events].forEach((event) => {
      const item = document.createElement("span");
      item.className = _isFailedExitCode(event.exit_code) ? "status-monitor-event-item status-monitor-event-failed" : "status-monitor-event-item";
      const code = _exitCodeLabel(event.exit_code).replace("exit ", "exit=");
      item.textContent = `${event.root || "run"} ${code} ${_formatDurationSeconds(event.elapsed_seconds)} · ${_truncateText(event.command || "", 44)}`;
      row.appendChild(item);
    });
  }
  function _applyEventTicker(ticker) {
    const events = _eventTickerEvents();
    const signature = _eventTickerSignature(events);
    if (ticker.dataset.eventSignature === signature) return;
    ticker.dataset.eventSignature = signature;
    const row = ticker.querySelector(".status-monitor-event-row");
    if (row) _populateEventTickerRow(row, events);
  }
  function _visualGridSignature() {
    const insights = cachedInsights || {};
    const windows = insights.windows && typeof insights.windows === "object" ? insights.windows : {};
    const activity = Array.isArray(insights.activity) ? insights.activity : [];
    const commandMix = Array.isArray(insights.command_mix) ? insights.command_mix : [];
    const constellation = Array.isArray(insights.constellation) ? insights.constellation : [];
    const firstActivity = activity[0] || {};
    const lastActivity = activity[activity.length - 1] || {};
    const firstStar = constellation[0] || {};
    const lastStar = constellation[constellation.length - 1] || {};
    const windowSignature = ["activity", "command_mix", "constellation"].map((key) => {
      const windowInfo = windows[key] && typeof windows[key] === "object" ? windows[key] : {};
      return [
        key,
        Number(windowInfo.days || 0),
        Number(windowInfo.total_runs || 0),
        Number(windowInfo.plotted_runs || 0),
        Number(windowInfo.available_runs || 0)
      ].join(",");
    }).join("|");
    const activitySignature = [
      activity.length,
      firstActivity.date || "",
      lastActivity.date || "",
      Number(lastActivity.count || 0),
      Number(lastActivity.succeeded || 0),
      Number(lastActivity.failed || 0),
      Number(lastActivity.incomplete || 0)
    ].join(":");
    const commandSignature = commandMix.map((item) => [
      item.root || "",
      item.category || "",
      Number(item.count || 0),
      Number(item.succeeded || 0),
      Number(item.failed || 0),
      Number(item.incomplete || 0),
      Number(item.total_elapsed_seconds || 0).toFixed(0)
    ].join(",")).join("|");
    const constellationSignature = [
      constellation.length,
      firstStar.id || "",
      lastStar.id || "",
      lastStar.started || "",
      lastStar.finished || "",
      lastStar.exit_code ?? "active",
      Number(lastStar.output_line_count || 0)
    ].join(":");
    return [
      insights.first_run_date || "",
      Number(insights.max_day_count || 0),
      windowSignature,
      activitySignature,
      commandSignature,
      constellationSignature
    ].join("::");
  }
  function _renderEventTicker() {
    const events = _eventTickerEvents();
    const ticker = document.createElement("section");
    ticker.className = "status-monitor-event-ticker";
    ticker.dataset.eventSignature = _eventTickerSignature(events);
    const label = document.createElement("div");
    label.className = "status-monitor-event-label";
    label.textContent = "event stream";
    const track = document.createElement("div");
    track.className = "status-monitor-event-track";
    const row = document.createElement("div");
    row.className = "status-monitor-event-row";
    _populateEventTickerRow(row, events);
    track.appendChild(row);
    ticker.append(label, track);
    return ticker;
  }
  function _renderVisualShowcaseGrid() {
    const grid = document.createElement("div");
    grid.className = "status-monitor-showcase-grid";
    grid.dataset.visualSignature = _visualGridSignature();
    grid.append(_renderConstellationPanel(), _renderTreemapPanel(), _renderHeatmapPanel());
    return grid;
  }
  function _renderVisualShowcaseSection(activeRuns, options = {}) {
    const section = document.createElement("section");
    section.className = "status-monitor-showcase";
    section.appendChild(_renderPulseStrip(activeRuns));
    section.appendChild(_renderActiveRunsSection(activeRuns, options));
    section.append(_renderVisualShowcaseGrid(), _renderEventTicker());
    return section;
  }
  function _updateVisualShowcaseSection(section, activeRuns, options = {}) {
    const pulseStrip = section.querySelector(":scope > .status-monitor-pulse-strip");
    if (pulseStrip) {
      _applyPulseStrip(pulseStrip, activeRuns);
    } else {
      section.prepend(_renderPulseStrip(activeRuns));
    }
    const runsSection = section.querySelector(":scope > .status-monitor-runs-section");
    if (runsSection) {
      _applyActiveRunsSection(runsSection, activeRuns, options);
    } else {
      const fresh = _renderActiveRunsSection(activeRuns, options);
      const pulse = section.querySelector(":scope > .status-monitor-pulse-strip");
      if (pulse) pulse.after(fresh);
      else section.appendChild(fresh);
    }
    const grid = section.querySelector(":scope > .status-monitor-showcase-grid");
    const nextSignature = _visualGridSignature();
    if (!grid) {
      const ticker2 = section.querySelector(":scope > .status-monitor-event-ticker");
      section.insertBefore(_renderVisualShowcaseGrid(), ticker2 || null);
    } else if (grid.dataset.visualSignature !== nextSignature) {
      grid.replaceWith(_renderVisualShowcaseGrid());
    }
    const ticker = section.querySelector(":scope > .status-monitor-event-ticker");
    if (ticker) {
      _applyEventTicker(ticker);
    } else {
      section.appendChild(_renderEventTicker());
    }
  }
  function _replaceDashboardChildren(children) {
    children.forEach((child, index) => {
      const current = listEl?.children[index];
      if (current === child) return;
      if (current) {
        current.replaceWith(child);
      } else {
        listEl?.appendChild(child);
      }
    });
    while (listEl && listEl.children.length > children.length) {
      listEl.lastElementChild?.remove();
    }
  }
  function _renderServicesSection() {
    const status = cachedStatus || {};
    const section = _statusSection("System", status.error ? "status unavailable" : "");
    const uptime = _statusMonitorUptimeText(status);
    const latency = _isTelemetryNumber(status.latency_ms) ? Number(status.latency_ms) : null;
    section.appendChild(_statusGrid([
      _statusCard({
        label: "Database",
        value: _statusLabel(status.db),
        tone: _statusTone(status.db)
      }),
      _statusCard({
        label: "Redis",
        value: _statusLabel(status.redis),
        tone: _statusTone(status.redis)
      }),
      _statusCard({
        label: "Transport",
        value: "SSE",
        tone: "ok"
      }),
      _statusCard({
        label: "Uptime",
        value: uptime,
        meta: latency === null ? "" : `${latency} ms poll`,
        tone: "idle",
        valueDataset: { statusMonitorUptimeValue: "1" }
      })
    ]));
    return section;
  }
  function _renderWorkspaceSection() {
    const workspace = cachedWorkspace || {};
    const usage = workspace.usage || {};
    const limits = workspace.limits || {};
    const quotaBytes = Number(limits.quota_bytes || 0);
    const bytesUsed = Number(usage.bytes_used || 0);
    const maxFiles = Number(limits.max_files || 0);
    const fileCount = Number(usage.file_count || 0);
    const quotaPercent = quotaBytes > 0 ? bytesUsed / quotaBytes * 100 : null;
    const filePercent = maxFiles > 0 ? fileCount / maxFiles * 100 : null;
    const section = _statusSection("Resources", workspace.error ? workspace.error : "session workspace");
    section.appendChild(_statusGrid([
      _statusCard({
        label: "Workspace quota",
        value: workspace.enabled === false ? "disabled" : _formatMemoryBytes(bytesUsed),
        meta: quotaBytes > 0 ? `${_formatPercent(quotaPercent)} of ${_formatMemoryBytes(quotaBytes)}` : "",
        tone: workspace.enabled === false ? "idle" : "ok",
        meterPercent: quotaPercent
      }),
      _statusCard({
        label: "Workspace files",
        value: workspace.enabled === false ? "disabled" : _formatCount(fileCount),
        meta: maxFiles > 0 ? `${_formatPercent(filePercent)} of ${_formatCount(maxFiles)} files` : "",
        tone: workspace.enabled === false ? "idle" : "ok",
        meterPercent: filePercent
      })
    ], "status-monitor-grid-two"));
    return section;
  }
  function _renderSessionStatsSection(activeCount) {
    const stats = cachedStats || {};
    const runs = stats.runs || {};
    const total = Number(runs.total || 0);
    const succeeded = Number(runs.succeeded || 0);
    const failed = Number(runs.failed || 0);
    const incomplete = Number(runs.incomplete || 0);
    const completed = succeeded + failed;
    const successRate = completed > 0 ? succeeded / completed * 100 : 0;
    const section = _statusSection("Session", stats.error ? "stats unavailable" : "");
    section.appendChild(_statusGrid([
      _statusCard({
        label: "Runs",
        value: _formatCount(total),
        meta: `${_formatCount(activeCount)} active`,
        tone: activeCount > 0 ? "ok" : "idle"
      }),
      _statusCard({
        label: "Success rate",
        value: completed > 0 ? _formatPercent(successRate) : "n/a",
        meta: `${_formatCount(succeeded)} ok / ${_formatCount(failed)} failed`,
        tone: failed > 0 ? "warn" : "ok",
        meterPercent: completed > 0 ? successRate : null
      }),
      _statusCard({
        label: "Average elapsed",
        value: _formatDurationSeconds(runs.average_elapsed_seconds),
        meta: incomplete > 0 ? `${_formatCount(incomplete)} incomplete` : "",
        tone: "idle"
      }),
      _statusCard({
        label: "Starred",
        value: _formatCount(stats.starred_commands || 0),
        meta: `${_formatCount(stats.snapshots || 0)} snapshots`,
        tone: "idle"
      })
    ]));
    return section;
  }
  function _activeRunsSummary(runs, loading) {
    if (loading) return "Loading active runs";
    return runs.length === 1 ? "1 active run" : `${runs.length} active runs`;
  }
  function _gcResourceStateForRuns(runs) {
    _statusMonitorResources().gcForRuns(runs);
  }
  function _populateActiveRunMeta(meta, run) {
    const tabLabel = _tabLabelForRun(run);
    const elapsed = document.createElement("span");
    elapsed.className = "status-monitor-meta-chip status-monitor-elapsed";
    elapsed.setAttribute("data-status-monitor-started", String(run?.started || ""));
    elapsed.textContent = _formatElapsed(run?.started);
    const chips = [
      _runMetaChip(`run ${_shortRunId(run)}`),
      _runMetaChip(`pid ${run?.pid || "-"}`),
      elapsed
    ];
    if (tabLabel) {
      chips.push(_runMetaChip(tabLabel, "status-monitor-meta-chip-tab"));
    }
    if (run?.has_live_owner && !run?.owned_by_this_client) {
      chips.push(_runMetaChip("another browser", "status-monitor-meta-chip-warn"));
    } else if (run?.owned_by_this_client) {
      chips.push(_runMetaChip("started here", "status-monitor-meta-chip-ok"));
    }
    meta.replaceChildren(...chips);
    meta.dataset.metaSignature = [
      tabLabel || "",
      run?.has_live_owner ? "1" : "0",
      run?.owned_by_this_client ? "1" : "0"
    ].join("|");
  }
  function _activeRunMetaSignature(run) {
    return [
      _tabLabelForRun(run) || "",
      run?.has_live_owner ? "1" : "0",
      run?.owned_by_this_client ? "1" : "0"
    ].join("|");
  }
  function _activeRunActionsSignature(run) {
    const ptyUnavailable = _isPtyRun(run) && !_tabForRun(run) && typeof _attachInteractivePtyCommand() !== "function";
    const hasAttach = typeof activateTabFn === "function" && !!_tabForRun(run) || !_isPtyRun(run) && typeof attachActiveRunFromMonitorFn === "function" || _isPtyRun(run) && typeof _attachInteractivePtyCommand() === "function";
    const hasKill = typeof killActiveRunFromMonitorFn === "function";
    return [
      hasAttach ? "A" : "",
      ptyUnavailable ? "P" : "",
      ptyUnavailable ? _ptyAttachUnavailableMessage(run) : "",
      hasKill ? "K" : ""
    ].join("|");
  }
  function _openOrAttachActiveRun(run) {
    const currentTab = _tabForRun(run);
    if (currentTab && typeof activateTabFn === "function") {
      activateTabFn(currentTab.id, { focusComposer: false });
      return Promise.resolve(true);
    }
    if (_isPtyRun(run)) {
      const attachPty = _attachInteractivePtyCommand();
      if (typeof attachPty === "function") {
        return Promise.resolve(attachPty(run));
      }
      if (typeof showToastFn === "function") showToastFn(_ptyAttachUnavailableMessage(run), "error");
      return Promise.resolve(false);
    }
    if (!_isPtyRun(run) && typeof attachActiveRunFromMonitorFn === "function") {
      return Promise.resolve(attachActiveRunFromMonitorFn(run));
    }
    return Promise.resolve(false);
  }
  function _renderActiveRunActions(run) {
    const actions = document.createElement("div");
    actions.className = "status-monitor-actions";
    actions.dataset.actionsSignature = _activeRunActionsSignature(run);
    if (typeof activateTabFn === "function" && !!_tabForRun(run) || !_isPtyRun(run) && typeof attachActiveRunFromMonitorFn === "function" || _isPtyRun(run) && typeof _attachInteractivePtyCommand() === "function") {
      actions.append(_statusMonitorActionButton("Attach", "Open or attach this run in a tab", () => {
        const latest = activeRunByRow.get(actions.closest(".status-monitor-item")) || run;
        return _openOrAttachActiveRun(latest);
      }));
    } else if (_isPtyRun(run)) {
      const unavailable = _statusMonitorActionButton("Attach", _ptyAttachUnavailableMessage(run), () => {
        const latest = activeRunByRow.get(actions.closest(".status-monitor-item")) || run;
        return _openOrAttachActiveRun(latest);
      }, {
        className: "status-monitor-action-btn-disabled",
        closeOnSuccess: false
      });
      unavailable.setAttribute("aria-disabled", "true");
      actions.append(unavailable);
    }
    if (typeof killActiveRunFromMonitorFn === "function") {
      actions.append(_statusMonitorActionButton("Kill", "Kill this active run", () => {
        const latest = activeRunByRow.get(actions.closest(".status-monitor-item")) || run;
        return killActiveRunFromMonitorFn(latest);
      }, { className: "status-monitor-action-btn-kill", closeOnSuccess: false }));
    }
    return actions;
  }
  function _renderActiveRunRow(run) {
    const item = document.createElement("article");
    item.className = "status-monitor-item chrome-row row-accent-green";
    item.dataset.runId = String(run?.run_id || run?.id || "");
    activeRunByRow.set(item, run);
    const openRun = () => {
      const latest = activeRunByRow.get(item) || run;
      return _openOrAttachActiveRun(latest).then((attached) => {
        if (attached) closeStatusMonitor();
        return attached;
      });
    };
    const tab = _tabForRun(run);
    if (tab || !_isPtyRun(run) && typeof attachActiveRunFromMonitorFn === "function" || _isPtyRun(run) && typeof _attachInteractivePtyCommand() === "function" || _isPtyRun(run)) {
      item.classList.add("status-monitor-item-clickable", "chrome-row-clickable");
      item.setAttribute("role", "button");
      item.setAttribute("tabindex", "0");
      item.setAttribute("aria-label", `${tab ? "Open tab for" : _isPtyRun(run) ? "Show PTY attach note for" : "Attach to"} ${String(run?.command || "active run")}`);
      item.addEventListener("click", (event) => {
        if (event.target && event.target.closest && event.target.closest(".status-monitor-action-btn")) return;
        openRun().catch((err) => {
          if (typeof showToastFn === "function") showToastFn(err?.message || "Could not open run", "error");
        });
      });
      item.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        openRun().catch((err) => {
          if (typeof showToastFn === "function") showToastFn(err?.message || "Could not open run", "error");
        });
      });
    }
    const command = document.createElement("div");
    command.className = "status-monitor-command";
    command.textContent = String(run?.command || "").trim() || "(unknown command)";
    const meta = document.createElement("div");
    meta.className = "status-monitor-meta";
    _populateActiveRunMeta(meta, run);
    const details = document.createElement("div");
    details.className = "status-monitor-details";
    details.append(command, meta);
    const ptyNoticeText = _ptyAttachUnavailableMessage(run);
    if (ptyNoticeText) {
      const ptyNotice = document.createElement("div");
      ptyNotice.className = "status-monitor-pty-note";
      ptyNotice.textContent = ptyNoticeText;
      details.appendChild(ptyNotice);
    }
    const usage = _runResourceUsage(run);
    const telemetry = _runSparklinePanel(run, usage);
    const cpuValue = _formatCpuPercent(usage.cpu_percent);
    const cpuCollecting = cpuValue === "collecting";
    const meters = document.createElement("div");
    meters.className = "status-monitor-meters";
    meters.append(
      _statusMonitorMeter({
        label: "CPU",
        value: cpuCollecting ? "" : cpuValue,
        percent: usage.cpu_percent,
        className: "status-monitor-meter-cpu",
        collecting: cpuCollecting,
        ariaValue: cpuValue
      }),
      _statusMonitorMeter({
        label: "MEM",
        value: _formatMemoryBytes(usage.memory_bytes),
        percent: _memoryPercent(usage.memory_bytes),
        className: "status-monitor-meter-mem"
      })
    );
    const meterRail = document.createElement("div");
    meterRail.className = "status-monitor-meter-rail";
    meterRail.appendChild(meters);
    const actions = _renderActiveRunActions(run);
    if (actions.childElementCount) meterRail.append(actions);
    item.append(details, telemetry, meterRail);
    return item;
  }
  function _updateActiveRunRow(row, run) {
    activeRunByRow.set(row, run);
    const meta = row.querySelector(":scope > .status-monitor-details > .status-monitor-meta");
    if (meta && meta.dataset.metaSignature !== _activeRunMetaSignature(run)) {
      _populateActiveRunMeta(meta, run);
    } else if (meta) {
      const elapsed = meta.querySelector(".status-monitor-elapsed");
      if (elapsed) {
        const started = String(run?.started || "");
        if (elapsed.getAttribute("data-status-monitor-started") !== started) {
          elapsed.setAttribute("data-status-monitor-started", started);
          elapsed.textContent = _formatElapsed(run?.started);
        }
      }
    }
    const details = row.querySelector(":scope > .status-monitor-details");
    if (details) {
      const expectedNotice = _ptyAttachUnavailableMessage(run);
      let notice = details.querySelector(":scope > .status-monitor-pty-note");
      if (expectedNotice) {
        if (!notice) {
          notice = document.createElement("div");
          notice.className = "status-monitor-pty-note";
          details.appendChild(notice);
        }
        if (notice.textContent !== expectedNotice) notice.textContent = expectedNotice;
      } else if (notice) {
        notice.remove();
      }
    }
    const usage = _runResourceUsage(run);
    const samples = _recordResourceTrend(run, usage);
    const cpuPath = row.querySelector(".status-monitor-sparkline-cpu");
    const memPath = row.querySelector(".status-monitor-sparkline-mem");
    if (cpuPath) cpuPath.setAttribute("d", _trendPath(samples, "cpu"));
    if (memPath) memPath.setAttribute("d", _trendPath(samples, "mem"));
    const cpuValue = _formatCpuPercent(usage.cpu_percent);
    const cpuCollecting = cpuValue === "collecting";
    const cpuMeter = row.querySelector(".status-monitor-meter-cpu");
    if (cpuMeter) {
      _updateStatusMonitorMeter(cpuMeter, {
        label: "CPU",
        value: cpuCollecting ? "" : cpuValue,
        percent: usage.cpu_percent,
        collecting: cpuCollecting,
        ariaValue: cpuValue
      });
    }
    const memMeter = row.querySelector(".status-monitor-meter-mem");
    if (memMeter) {
      _updateStatusMonitorMeter(memMeter, {
        label: "MEM",
        value: _formatMemoryBytes(usage.memory_bytes),
        percent: _memoryPercent(usage.memory_bytes)
      });
    }
    const meterRail = row.querySelector(":scope > .status-monitor-meter-rail");
    if (meterRail) {
      const expectedSig = _activeRunActionsSignature(run);
      const existingActions = meterRail.querySelector(":scope > .status-monitor-actions");
      if (!expectedSig) {
        if (existingActions) existingActions.remove();
      } else if (!existingActions) {
        meterRail.append(_renderActiveRunActions(run));
      } else if (existingActions.dataset.actionsSignature !== expectedSig) {
        existingActions.replaceWith(_renderActiveRunActions(run));
      }
    }
  }
  function _renderActiveRunsSection(runs, options = {}) {
    const loading = !!options.loadingActiveRuns;
    const section = _statusSection("Runs", _activeRunsSummary(runs, loading));
    section.classList.add("status-monitor-runs-section");
    const runList = document.createElement("div");
    runList.className = "status-monitor-runs-list";
    section.appendChild(runList);
    _applyActiveRunsSection(section, runs, options);
    return section;
  }
  function _applyActiveRunsSection(section, runs, options = {}) {
    const loading = !!options.loadingActiveRuns;
    const summary = _activeRunsSummary(runs, loading);
    const header = section.querySelector(":scope > .status-monitor-section-header");
    if (header) {
      let metaEl = header.querySelector(":scope > .status-monitor-section-meta");
      if (summary) {
        if (!metaEl) {
          metaEl = document.createElement("div");
          metaEl.className = "status-monitor-section-meta";
          header.appendChild(metaEl);
        }
        if (metaEl.textContent !== summary) metaEl.textContent = summary;
      } else if (metaEl) {
        metaEl.remove();
      }
    }
    section.dataset.activeRunCount = String(runs.length);
    const runList = section.querySelector(":scope > .status-monitor-runs-list");
    if (!runList) return;
    runList.classList.toggle("status-monitor-runs-list-many", runs.length >= 5);
    runList.classList.toggle("status-monitor-runs-list-medium", runs.length >= 3 && runs.length < 5);
    if (loading) {
      const existingEmpty = runList.querySelector(":scope > .status-monitor-empty");
      if (existingEmpty && existingEmpty.textContent === "Loading active runs..." && runList.children.length === 1) {
        return;
      }
      const empty = document.createElement("div");
      empty.className = "status-monitor-empty status-monitor-runs-empty";
      empty.textContent = "Loading active runs...";
      runList.replaceChildren(empty);
      return;
    }
    _gcResourceStateForRuns(runs);
    const emptyNode = runList.querySelector(":scope > .status-monitor-empty");
    if (emptyNode) emptyNode.remove();
    if (!runs.length) {
      runList.querySelectorAll(":scope > .status-monitor-item").forEach((node) => node.remove());
      const empty = document.createElement("div");
      empty.className = "status-monitor-empty status-monitor-runs-empty";
      empty.textContent = "No active runs.";
      runList.appendChild(empty);
      return;
    }
    const existingRows = /* @__PURE__ */ new Map();
    runList.querySelectorAll(":scope > .status-monitor-item").forEach((node) => {
      const id = node.dataset.runId || "";
      if (id) existingRows.set(id, node);
    });
    const seen = /* @__PURE__ */ new Set();
    let cursor = null;
    for (const run of runs) {
      const id = String(run?.run_id || run?.id || "");
      if (!id) continue;
      seen.add(id);
      let row = existingRows.get(id);
      if (row) {
        _updateActiveRunRow(row, run);
      } else {
        row = _renderActiveRunRow(run);
      }
      if (cursor) {
        if (cursor.nextSibling !== row) cursor.after(row);
      } else if (runList.firstChild !== row) {
        runList.insertBefore(row, runList.firstChild || null);
      }
      cursor = row;
    }
    for (const [id, row] of existingRows) {
      if (!seen.has(id)) row.remove();
    }
  }
  function _renderDashboard(runs, options = {}) {
    if (!listEl || !summaryEl) return;
    const activeRuns = Array.isArray(runs) ? runs : [];
    const showcase = listEl.querySelector(":scope > .status-monitor-showcase") || _renderVisualShowcaseSection(activeRuns, options);
    if (showcase.parentElement === listEl) _updateVisualShowcaseSection(showcase, activeRuns, options);
    const fallbackSummary = activeRuns.length === 1 ? "1 active run" : `${activeRuns.length} active runs`;
    if (summaryEl.dataset) {
      if (!options.loadingActiveRuns && latestPulseData?.summaryPrefix) {
        summaryEl.dataset.statusMonitorSummaryPrefix = latestPulseData.summaryPrefix;
      } else {
        delete summaryEl.dataset.statusMonitorSummaryPrefix;
      }
    }
    summaryEl.textContent = options.loadingActiveRuns ? "Loading active runs..." : latestPulseData?.meta || fallbackSummary;
    _replaceDashboardChildren([
      showcase,
      _renderServicesSection(),
      _renderWorkspaceSection(),
      _renderSessionStatsSection(activeRuns.length)
    ]);
    _updateElapsedTimers();
  }
  async function refreshStatusMonitor(options = {}) {
    _ensureMonitor();
    try {
      const previousRunCount = cachedRuns.length;
      const forceInsights = !!options.forceInsights;
      await _refreshDashboardData({ includeInsights: forceInsights });
      const runs = await _refreshActiveRunCache({ render: true });
      if (!forceInsights && previousRunCount > 0 && runs.length === 0) {
        await _refreshHistoryInsights();
        _renderDashboard(runs);
      }
      _scheduleOpenCpuFollowup(runs);
    } catch (err) {
      if (summaryEl) summaryEl.textContent = "Unavailable";
      if (listEl) {
        listEl.replaceChildren();
        const error = document.createElement("div");
        error.className = "status-monitor-empty status-monitor-error";
        error.textContent = err?.message || "Status monitor failed to load.";
        listEl.appendChild(error);
      }
    }
  }
  function _clearWarmupTimer() {
    if (warmupTimer) clearTimeout(warmupTimer);
    warmupTimer = null;
  }
  function _clearOpenFollowupTimer() {
    if (openFollowupTimer) clearTimeout(openFollowupTimer);
    openFollowupTimer = null;
  }
  function _scheduleOpenCpuFollowup(runs) {
    _clearOpenFollowupTimer();
    if (!isOpen || !_runsNeedCpuFollowup(runs)) return;
    openFollowupTimer = setTimeout(() => {
      openFollowupTimer = null;
      if (isOpen && document.visibilityState === "visible") void refreshStatusMonitor();
    }, CPU_SAMPLE_WARMUP_MS);
  }
  function _startClosedPolling() {
    if (closedPollTimer) return;
    closedPollTimer = setInterval(() => {
      if (isOpen || document.visibilityState !== "visible") return;
      void _refreshActiveRunCache({ render: false }).catch(() => {
      });
    }, CLOSED_POLL_MS);
  }
  function _stopClosedPolling() {
    if (closedPollTimer) clearInterval(closedPollTimer);
    closedPollTimer = null;
  }
  function _primeStatusMonitorSamples() {
    _clearWarmupTimer();
    if (document.visibilityState !== "visible") {
      _startClosedPolling();
      return;
    }
    void _refreshActiveRunCache({ render: isOpen }).then((runs) => {
      if (!runs.length) return;
      _startClosedPolling();
      warmupTimer = setTimeout(() => {
        warmupTimer = null;
        if (document.visibilityState === "visible") {
          void _refreshActiveRunCache({ render: isOpen }).catch(() => {
          });
        }
      }, CPU_SAMPLE_WARMUP_MS);
    }).catch(() => {
      _startClosedPolling();
    });
  }
  function _startPolling() {
    _stopClosedPolling();
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(() => {
      if (isOpen && document.visibilityState === "visible") void refreshStatusMonitor();
    }, POLL_MS);
    if (tickTimer) clearInterval(tickTimer);
    tickTimer = setInterval(() => {
      if (isOpen && document.visibilityState === "visible") {
        _updateElapsedTimers();
        _updateLiveUptimeDisplays();
      }
    }, 1e3);
    _startPulseAnimation();
  }
  function _stopPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
    if (tickTimer) clearInterval(tickTimer);
    tickTimer = null;
    _stopPulseAnimation();
  }
  async function openStatusMonitor(options = {}) {
    const source = String(options.source || "command");
    _ensureMonitor();
    isOpen = true;
    _positionMonitor();
    const mobile = _isMobileStatusMonitor();
    document.body.classList.toggle("status-monitor-mobile-open", mobile);
    document.body.classList.toggle("status-monitor-desktop-open", !mobile);
    monitorEl?.classList.toggle("chrome-drawer", !mobile);
    monitorEl?.classList.toggle("status-monitor-modal", !mobile);
    scrimEl?.classList.remove("u-hidden");
    monitorEl?.classList.remove("u-hidden");
    const syncModalOverlayStateFn = typeof syncModalOverlayState !== "undefined" && syncModalOverlayState || _statusMonitorGlobalFunction("syncModalOverlayState");
    syncModalOverlayStateFn?.();
    if (monitorEl) monitorEl.dataset.source = source;
    const pauseBackgroundStreams = typeof pauseBackgroundRunStreamsForStatusMonitor !== "undefined" && pauseBackgroundRunStreamsForStatusMonitor || _statusMonitorGlobalFunction("pauseBackgroundRunStreamsForStatusMonitor");
    if (typeof pauseBackgroundStreams === "function") pauseBackgroundStreams();
    _resetPulseVisualsForOpen();
    suppressPulseLoadUntilFresh = true;
    _renderDashboard([], { loadingActiveRuns: true });
    _startPolling();
    let runs = [];
    try {
      runs = await _refreshActiveRunCache({ render: false, renderWhileOpen: false });
    } catch (err) {
      suppressPulseLoadUntilFresh = false;
      closeStatusMonitor();
      if (typeof showToastFn === "function") showToastFn(err?.message || "Status monitor failed to load", "error");
      return false;
    }
    suppressPulseLoadUntilFresh = false;
    _renderDashboard(runs);
    await _refreshDashboardData({ includeInsights: true });
    _renderDashboard(runs);
    _scheduleOpenCpuFollowup(runs);
    return true;
  }
  function closeStatusMonitor() {
    isOpen = false;
    _stopPolling();
    _clearOpenFollowupTimer();
    if (cachedRuns.length && _activeHudStatusIsRunning()) _startClosedPolling();
    const resumeBackgroundStreams = typeof resumeBackgroundRunStreamsAfterStatusMonitor !== "undefined" && resumeBackgroundRunStreamsAfterStatusMonitor || _statusMonitorGlobalFunction("resumeBackgroundRunStreamsAfterStatusMonitor");
    if (typeof resumeBackgroundStreams === "function") resumeBackgroundStreams();
    document.body.classList.remove("status-monitor-mobile-open");
    document.body.classList.remove("status-monitor-desktop-open");
    scrimEl?.classList.add("u-hidden");
    monitorEl?.classList.add("u-hidden");
    const syncModalOverlayStateFn = typeof syncModalOverlayState !== "undefined" && syncModalOverlayState || _statusMonitorGlobalFunction("syncModalOverlayState");
    syncModalOverlayStateFn?.();
  }
  function isStatusMonitorOpen() {
    return isOpen;
  }
  function _makeHudCellOpenMonitor(cell, source, label) {
    if (!cell || cell.dataset.statusMonitorTrigger === "1") return;
    cell.dataset.statusMonitorTrigger = "1";
    cell.classList.add("hud-cell-clickable", "hud-action-cell");
    cell.setAttribute("role", "button");
    cell.setAttribute("tabindex", "0");
    cell.setAttribute("aria-haspopup", "dialog");
    cell.setAttribute("aria-label", label);
    cell.addEventListener("click", () => {
      void openStatusMonitor({ source });
    });
    cell.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      void openStatusMonitor({ source });
    });
  }
  function _clearStatusAffordance() {
    const cell = document.getElementById("hud-status-cell");
    if (!cell) return;
    cell.classList.remove("hud-status-expandable", "hud-status-affordance-pulse");
    cell.querySelector(".status-monitor-status-glyph")?.remove();
    cell.title = "";
  }
  function _activeHudStatusIsRunning() {
    return String(document.getElementById("status")?.textContent || "").trim().toUpperCase() === "RUNNING";
  }
  function _bindHudTriggers() {
    _makeHudCellOpenMonitor(
      document.getElementById("hud-status-cell"),
      "status",
      "Open status monitor from status"
    );
    _makeHudCellOpenMonitor(
      document.getElementById("hud-last-exit-cell") || document.getElementById("hud-last-exit")?.closest(".hud-cell"),
      "last-exit",
      "Open status monitor from last exit"
    );
    _makeHudCellOpenMonitor(
      document.getElementById("hud-tabs-cell") || document.getElementById("hud-tabs")?.closest(".hud-cell"),
      "tabs",
      "Open status monitor from tabs"
    );
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && isOpen) closeStatusMonitor();
  });
  document.addEventListener("visibilitychange", () => {
    if (isOpen && document.visibilityState === "visible") {
      _startPulseAnimation();
      void refreshStatusMonitor();
    } else if (isOpen) {
      _stopPulseAnimation();
    } else if (document.visibilityState === "visible" && cachedRuns.length) {
      _primeStatusMonitorSamples();
    }
  });
  document.addEventListener("app:status-changed", (event) => {
    const status = String(event?.detail?.status || "").trim().toLowerCase();
    _clearStatusAffordance();
    if (status === "running") {
      _primeStatusMonitorSamples();
    } else if (!isOpen) {
      _clearWarmupTimer();
      _stopClosedPolling();
    }
  });
  window.addEventListener("resize", () => {
    if (!isOpen) return;
    _positionMonitor();
    document.querySelectorAll(".status-monitor-constellation").forEach(_scheduleConstellationAspectSync);
  });
  _bindHudTriggers();
  _clearStatusAffordance();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _bindHudTriggers, { once: true });
  }
  if (typeof setRuntimeHandlers === "function") {
    setRuntimeHandlers({ openStatusMonitor, refreshStatusMonitor });
  }
  exportedOpenStatusMonitor = openStatusMonitor;
  exportedCloseStatusMonitor = closeStatusMonitor;
  exportedIsStatusMonitorOpen = isStatusMonitorOpen;
  exportedRefreshStatusMonitor = refreshStatusMonitor;
  exportedConstellationTestHelpers = {
    hourDensity: _constellationHourDensity,
    activeWindow: _constellationActiveWindow,
    deadBands: _constellationDeadBands,
    visibleSegments: _constellationVisibleSegments,
    minuteToX: _constellationMinuteToX,
    plotLeft: CONSTELLATION_PLOT_LEFT,
    plotWidth: CONSTELLATION_PLOT_WIDTH
  };
})(typeof window !== "undefined" ? window : globalThis);
export {
  exportedConstellationTestHelpers as __constellationTestHelpers,
  exportedCloseStatusMonitor as closeStatusMonitor,
  exportedIsStatusMonitorOpen as isStatusMonitorOpen,
  exportedOpenStatusMonitor as openStatusMonitor,
  exportedRefreshStatusMonitor as refreshStatusMonitor
};
