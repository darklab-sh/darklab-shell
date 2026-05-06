// ── App-native status monitor ──
// First-class session/status surface: centered modal on desktop, bottom sheet
// on mobile. Active-run attach/kill remains the bottom section.

(function () {
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

  const POLL_MS = 3000;
  const CLOSED_POLL_MS = 8000;
  const CPU_SAMPLE_WARMUP_MS = 900;
  const resourceStateByRunId = new Map();
  const resourceTrendByRunId = new Map();
  const pulseStateByStrip = new WeakMap();
  const pulseNodeCacheByStrip = new WeakMap();
  const activeRunByRow = new WeakMap();
  const categoryToneCache = new Map();
  const constellationPopoverTimerByPanel = new WeakMap();
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const PULSE_BASELINE_Y = 40;
  const PULSE_VIEW_WIDTH = 720;
  const PULSE_PATH_MARGIN = 240;
  const PULSE_SCROLL_PX_PER_MS = 0.072;
  const PULSE_FRAME_MS = 1000 / 45;
  const PULSE_FRESH_LIVE_WINDOW = 104;
  const PULSE_CPU_BUCKET_HYSTERESIS = 8;
  const PULSE_RECENT_CPU_SAMPLE_LIMIT = 8;
  const CONSTELLATION_POPOVER_MOVE_DELAY_MS = 80;
  const CONSTELLATION_PLOT_LEFT = 38;
  const CONSTELLATION_PLOT_WIDTH = 580;
  const CONSTELLATION_PLOT_RIGHT = CONSTELLATION_PLOT_LEFT + CONSTELLATION_PLOT_WIDTH;
  const CONSTELLATION_Y_BASELINE = 260;
  const CONSTELLATION_Y_RANGE = 205;
  const DAY_MS = 86400000;
  const GRACEFUL_TERMINATION_EXIT_CODES = new Set([-15]);

  function _normalizedExitCode(exitCode) {
    if (exitCode === null || exitCode === undefined || exitCode === '') return null;
    const number = Number(exitCode);
    return Number.isFinite(number) ? number : null;
  }

  function _isGracefulTerminationExitCode(exitCode) {
    const code = _normalizedExitCode(exitCode);
    return code !== null && GRACEFUL_TERMINATION_EXIT_CODES.has(code);
  }

  function _isFailedExitCode(exitCode) {
    const code = _normalizedExitCode(exitCode);
    return code !== null && code !== 0 && !GRACEFUL_TERMINATION_EXIT_CODES.has(code);
  }

  function _exitCodeLabel(exitCode) {
    const code = _normalizedExitCode(exitCode);
    if (code === null) return 'active';
    if (_isGracefulTerminationExitCode(code)) return 'terminated';
    return `exit ${code}`;
  }

  function _isMobileStatusMonitor() {
    return !!(
      document.body?.classList?.contains('mobile-terminal-mode')
      || (window.matchMedia && window.matchMedia('(max-width: 600px)').matches)
    );
  }

  function _formatElapsed(started) {
    const start = Date.parse(String(started || ''));
    if (!Number.isFinite(start)) return '-';
    const total = Math.max(0, Math.floor((Date.now() - start) / 1000));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = total % 60;
    return [hours, minutes, seconds].map(value => String(value).padStart(2, '0')).join(':');
  }

  function _shortRunId(run) {
    return String(run?.run_id || run?.id || '').slice(0, 8) || '-';
  }

  function _formatCpuPercent(value) {
    if (value === null || value === undefined) return 'n/a';
    if (!Number.isFinite(Number(value))) return 'collecting';
    const cpu = Math.min(100, Math.max(0, Number(value)));
    return `${cpu.toFixed(cpu >= 10 ? 0 : 1)}%`;
  }

  function _isTelemetryNumber(value) {
    return value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));
  }

  function _runResourceUsage(run) {
    const runId = String(run?.run_id || run?.id || '');
    const usage = run?.resource_usage && typeof run.resource_usage === 'object'
      ? run.resource_usage
      : {};
    const previous = runId ? resourceStateByRunId.get(runId) : null;
    const now = Date.now();
    const cpuSeconds = _isTelemetryNumber(usage.cpu_seconds)
      ? Number(usage.cpu_seconds)
      : null;
    let cpuPercent = previous?.cpu_percent;
    if (cpuSeconds !== null && previous && _isTelemetryNumber(previous.cpu_seconds)) {
      const elapsedSeconds = Math.max(0, (now - Number(previous.sampled_at || now)) / 1000);
      const deltaCpu = cpuSeconds - Number(previous.cpu_seconds);
      if (elapsedSeconds >= 0.25 && deltaCpu >= 0) {
        cpuPercent = (deltaCpu / elapsedSeconds) * 100;
      }
    }
    if (cpuSeconds !== null && !_isTelemetryNumber(cpuPercent)) {
      cpuPercent = Number.NaN;
    }
    const memoryBytes = _isTelemetryNumber(usage.memory_bytes)
      ? Number(usage.memory_bytes)
      : previous?.memory_bytes;
    const resolved = {
      cpu_percent: cpuPercent,
      cpu_seconds: cpuSeconds ?? previous?.cpu_seconds,
      memory_bytes: memoryBytes,
      sampled_at: cpuSeconds !== null ? now : previous?.sampled_at,
    };
    if (runId && (
      _isTelemetryNumber(resolved.cpu_percent)
      || _isTelemetryNumber(resolved.cpu_seconds)
      || _isTelemetryNumber(resolved.memory_bytes)
    )) {
      resourceStateByRunId.set(runId, resolved);
    }
    return resolved;
  }

  function _recordResourceTrend(run, usage) {
    const runId = String(run?.run_id || run?.id || '');
    if (!runId) return [];
    const samples = resourceTrendByRunId.get(runId) || [];
    const now = Date.now();
    const previous = samples[samples.length - 1];
    if (!previous || now - previous.t >= 750) {
      samples.push({
        t: now,
        cpu: _isTelemetryNumber(usage.cpu_percent) ? Number(usage.cpu_percent) : null,
        mem: _isTelemetryNumber(usage.memory_bytes) ? Number(usage.memory_bytes) : null,
      });
      while (samples.length > 60) samples.shift();
      resourceTrendByRunId.set(runId, samples);
    }
    return samples;
  }

  function _trendPath(samples, key, width = 160, height = 34) {
    const values = samples.map(sample => sample[key]).filter(value => _isTelemetryNumber(value));
    if (!values.length) {
      const y = height / 2;
      return `M0 ${y} L${width} ${y}`;
    }
    const max = key === 'cpu'
      ? Math.max(100, ...values)
      : Math.max(...values, 1);
    const min = key === 'cpu' ? 0 : Math.min(...values, 0);
    const spread = Math.max(1, max - min);
    const points = samples.map((sample, index) => {
      const value = _isTelemetryNumber(sample[key]) ? Number(sample[key]) : min;
      const x = samples.length <= 1 ? width : (index / (samples.length - 1)) * width;
      const y = height - (((value - min) / spread) * (height - 6)) - 3;
      return [x, y];
    });
    return _pathFromPoints(points);
  }

  function _runMetaChip(text, className = '') {
    const chip = document.createElement('span');
    chip.className = `status-monitor-meta-chip ${className}`.trim();
    chip.textContent = text;
    return chip;
  }

  function _runSparklinePanel(run, usage) {
    const samples = _recordResourceTrend(run, usage);
    const panel = document.createElement('div');
    panel.className = 'status-monitor-spark-panel';

    const header = document.createElement('div');
    header.className = 'status-monitor-spark-header';
    const title = document.createElement('span');
    title.className = 'status-monitor-spark-title';
    title.textContent = 'CPU/MEM 60s';
    header.append(title);

    const svg = _svgEl('svg', {
      class: 'status-monitor-sparkline',
      viewBox: '0 0 160 34',
      role: 'img',
      'aria-label': 'CPU and memory trend',
      preserveAspectRatio: 'none',
    });
    svg.append(
      _svgEl('path', {
        class: 'status-monitor-sparkline-grid',
        d: 'M0 17 L160 17 M40 0 L40 34 M80 0 L80 34 M120 0 L120 34',
      }),
      _svgEl('path', { class: 'status-monitor-sparkline-cpu', d: _trendPath(samples, 'cpu') }),
      _svgEl('path', { class: 'status-monitor-sparkline-mem', d: _trendPath(samples, 'mem') }),
    );

    panel.append(header, svg);
    return panel;
  }

  function _runsNeedCpuFollowup(runs) {
    return (Array.isArray(runs) ? runs : []).some((run) => {
      const runId = String(run?.run_id || run?.id || '');
      if (!runId) return false;
      const state = resourceStateByRunId.get(runId);
      return state && _isTelemetryNumber(state.cpu_seconds) && !_isTelemetryNumber(state.cpu_percent);
    });
  }

  function _formatMemoryBytes(value) {
    if (value === null || value === undefined) return 'n/a';
    const bytes = Number(value);
    if (!Number.isFinite(bytes) || bytes < 0) return '-';
    const units = ['B', 'KB', 'MB', 'GB'];
    let size = bytes;
    let unitIndex = 0;
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex += 1;
    }
    const precision = unitIndex === 0 || size >= 10 ? 0 : 1;
    return `${size.toFixed(precision)} ${units[unitIndex]}`;
  }

  function _formatDurationSeconds(value) {
    if (!_isTelemetryNumber(value)) return 'n/a';
    const total = Math.max(0, Number(value));
    if (total >= 3600) {
      const hours = Math.floor(total / 3600);
      const minutes = Math.floor((total % 3600) / 60);
      return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
    }
    if (total >= 60) {
      const minutes = Math.floor(total / 60);
      const seconds = Math.round(total % 60);
      return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`;
    }
    return `${total.toFixed(total >= 10 ? 0 : 1)}s`;
  }

  function _currentStatusUptimeSeconds(status = cachedStatus) {
    if (!status || !_isTelemetryNumber(status.uptime)) return null;
    const base = Number(status.uptime);
    const receivedAt = Number(status.uptime_received_at_ms || 0);
    if (!Number.isFinite(receivedAt) || receivedAt <= 0) return base;
    return base + Math.max(0, (Date.now() - receivedAt) / 1000);
  }

  function _statusMonitorUptimeText(status = cachedStatus) {
    const uptime = _currentStatusUptimeSeconds(status);
    return uptime === null ? 'n/a' : _formatDurationSeconds(uptime);
  }

  function _formatCount(value) {
    const count = Number(value);
    if (!Number.isFinite(count)) return '0';
    return new Intl.NumberFormat().format(count);
  }

  function _insightWindowInfo(key, fallbackDays = 30) {
    const insights = cachedInsights || {};
    const windows = insights && typeof insights.windows === 'object' ? insights.windows : null;
    const info = windows && typeof windows[key] === 'object' ? windows[key] : null;
    const days = Number(info?.days || fallbackDays);
    const label = String(info?.label || '').trim();
    return {
      days,
      label: label || (days > 0 ? `last ${days} days` : ''),
    };
  }

  function _insightWindowLabel(key, fallbackDays = 30) {
    return _insightWindowInfo(key, fallbackDays).label;
  }

  function _truncateText(value, maxLength = 64) {
    const text = String(value || '').trim();
    if (text.length <= maxLength) return text;
    return `${text.slice(0, Math.max(0, maxLength - 1))}…`;
  }

  function _hashString(value) {
    let hash = 0;
    const text = String(value || '');
    for (let index = 0; index < text.length; index += 1) {
      hash = ((hash << 5) - hash) + text.charCodeAt(index);
      hash |= 0;
    }
    return Math.abs(hash);
  }

  function _normalizedHash(value) {
    return _hashString(String(value || '').trim().toLowerCase());
  }

  function _categoryTone(category) {
    const normalized = String(category || '').trim().toLowerCase();
    const cached = categoryToneCache.get(normalized);
    if (cached) return cached;
    let tone = { hue: 0, saturation: 0 };
    if (normalized.includes('vulner')) tone = { hue: 28, saturation: 100 };
    else if (normalized.includes('tls') || normalized.includes('cert')) tone = { hue: 184, saturation: 100 };
    else if (normalized.includes('recon')) tone = { hue: 207, saturation: 100 };
    else if (normalized.includes('diagnostic')) tone = { hue: 92, saturation: 100 };
    else if (normalized.includes('utility')) tone = { hue: 258, saturation: 88 };
    categoryToneCache.set(normalized, tone);
    return tone;
  }

  function _categoryLegendLabel(category) {
    const normalized = String(category || '').trim().toLowerCase();
    if (normalized.includes('vulner')) return 'Vuln';
    if (normalized.includes('tls') || normalized.includes('cert')) return 'TLS';
    if (normalized.includes('recon')) return 'Recon';
    if (normalized.includes('diagnostic')) return 'Diag';
    if (normalized.includes('utility')) return 'Util';
    return _truncateText(category || 'Other', 12);
  }

  function _categoryLegend(items) {
    const counts = new Map();
    (Array.isArray(items) ? items : []).forEach((item) => {
      const category = String(item?.category || '').trim() || 'Other';
      const key = category.toLowerCase();
      const existing = counts.get(key) || { category, count: 0 };
      existing.count += Math.max(1, Number(item?.count || 1));
      counts.set(key, existing);
    });
    const entries = [...counts.values()]
      .sort((left, right) => right.count - left.count || left.category.localeCompare(right.category))
      .slice(0, 4);
    if (!entries.length) return null;
    const legend = document.createElement('div');
    legend.className = 'status-monitor-category-legend';
    entries.forEach(({ category }) => {
      const tone = _categoryTone(category);
      const item = document.createElement('span');
      item.className = 'status-monitor-category-legend-item';
      item.title = category;
      item.style.setProperty('--legend-hue', String(tone.hue));
      item.style.setProperty('--legend-saturation', `${tone.saturation}%`);
      const dot = document.createElement('span');
      dot.className = 'status-monitor-category-legend-dot';
      dot.setAttribute('aria-hidden', 'true');
      const label = document.createElement('span');
      label.className = 'status-monitor-category-legend-label';
      label.textContent = _categoryLegendLabel(category);
      item.append(dot, label);
      legend.appendChild(item);
    });
    return legend;
  }

  function _buildConstellationLegendKey({ modifier, ariaLabel, label }) {
    const item = document.createElement('span');
    item.className = `status-monitor-category-legend-item status-monitor-legend-key status-monitor-legend-key-${modifier}`;
    item.setAttribute('aria-label', ariaLabel);
    const glyph = document.createElement('span');
    glyph.className = `status-monitor-legend-key-glyph status-monitor-legend-key-glyph-${modifier}`;
    glyph.setAttribute('aria-hidden', 'true');
    if (modifier === 'size') {
      // Render literal mini-stars at the chart's actual min and max radii so
      // the legend visual is identical to what the viewer sees on the canvas.
      const small = _svgEl('svg', {
        class: 'status-monitor-legend-star-svg status-monitor-legend-star-svg-small',
        viewBox: '0 0 8 8',
        'aria-hidden': 'true',
      });
      small.appendChild(_svgEl('circle', {
        class: 'status-monitor-star',
        cx: 4,
        cy: 4,
        r: 1.8,
      }));
      const large = _svgEl('svg', {
        class: 'status-monitor-legend-star-svg status-monitor-legend-star-svg-large',
        viewBox: '0 0 18 18',
        'aria-hidden': 'true',
      });
      large.appendChild(_svgEl('circle', {
        class: 'status-monitor-star',
        cx: 9,
        cy: 9,
        r: 7,
      }));
      glyph.append(small, large);
    }
    const text = document.createElement('span');
    text.className = 'status-monitor-category-legend-label';
    text.textContent = label;
    item.append(glyph, text);
    return item;
  }

  function _seededUnit(seed) {
    const value = Math.sin(Number(seed) || 1) * 10000;
    return value - Math.floor(value);
  }

  function _ambientConstellationSeed() {
    if (typeof CLIENT_ID !== 'undefined' && CLIENT_ID) return _normalizedHash(`ambient:${CLIENT_ID}`);
    return _normalizedHash('ambient:darklab');
  }

  function _ambientConstellationStars() {
    const seed = _ambientConstellationSeed();
    const columns = 18;
    const rows = 8;
    const stars = [];
    for (let row = 0; row < rows; row += 1) {
      for (let column = 0; column < columns; column += 1) {
        const index = (row * columns) + column;
        const jitterX = _seededUnit(seed + (index * 37) + 11);
        const jitterY = _seededUnit(seed + (index * 53) + 19);
        const scale = _seededUnit(seed + (index * 71) + 23);
        const tone = _seededUnit(seed + (index * 89) + 31);
        const depth = _seededUnit(seed + (index * 113) + 59);
        const bright = depth > 0.88;
        const baseRadius = 0.85 + (scale * 1.25);
        const baseOpacity = 0.42 + (_seededUnit(seed + (index * 97) + 43) * 0.34);
        stars.push({
          x: 12 + ((column + (jitterX * 0.88) + 0.06) / columns) * 616,
          y: 12 + ((row + (jitterY * 0.86) + 0.07) / rows) * 276,
          radius: baseRadius + (bright ? 0.45 + (depth * 0.35) : 0),
          opacity: Math.min(0.92, baseOpacity + (bright ? 0.16 + ((depth - 0.88) * 0.75) : 0)),
          hue: tone > 0.86 ? 48 : 92 + (tone * 55),
          saturation: bright ? 92 : 72 + (tone * 16),
          lightness: bright ? 82 + ((depth - 0.88) * 32) : 68 + (scale * 8),
          glow: 2.5 + (scale * 3.5) + (bright ? 3.4 : 0),
          glowAlpha: bright ? 0.54 : 0.3,
        });
      }
    }
    return stars;
  }

  function _svgEl(tag, attrs = {}) {
    const el = document.createElementNS(SVG_NS, tag);
    Object.entries(attrs).forEach(([key, value]) => {
      if (value !== null && value !== undefined) el.setAttribute(key, String(value));
    });
    return el;
  }

  function _pathFromPoints(points) {
    if (!points.length) return '';
    return points.map((point, index) => `${index === 0 ? 'M' : 'L'}${point[0].toFixed(1)} ${point[1].toFixed(1)}`).join(' ');
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
    const parts = String(svg?.getAttribute?.('viewBox') || `0 0 ${viewBoxWidth} ${viewBoxHeight}`)
      .trim()
      .split(/\s+/)
      .map(Number);
    const minX = Number.isFinite(parts[0]) ? parts[0] : 0;
    const minY = Number.isFinite(parts[1]) ? parts[1] : 0;
    const width = Number.isFinite(parts[2]) && parts[2] > 0 ? parts[2] : Number(viewBoxWidth) || 1;
    const height = Number.isFinite(parts[3]) && parts[3] > 0 ? parts[3] : Number(viewBoxHeight) || 1;
    const preserve = String(svg?.getAttribute?.('preserveAspectRatio') || 'xMidYMid meet').trim();
    if (preserve === 'none' || preserve.startsWith('none ')) {
      return {
        x: ((Number(viewBoxX) - minX) / width) * plotWidth,
        y: ((Number(viewBoxY) - minY) / height) * plotHeight,
        plotWidth,
        plotHeight,
      };
    }
    const scaleX = plotWidth / width;
    const scaleY = plotHeight / height;
    const scale = preserve.includes('slice')
      ? Math.max(scaleX, scaleY)
      : Math.min(scaleX, scaleY);
    const renderedWidth = width * scale;
    const renderedHeight = height * scale;
    const align = preserve.split(/\s+/)[0] || 'xMidYMid';
    const offsetX = align.includes('xMin')
      ? 0
      : align.includes('xMax')
        ? plotWidth - renderedWidth
        : (plotWidth - renderedWidth) / 2;
    const offsetY = align.includes('YMin')
      ? 0
      : align.includes('YMax')
        ? plotHeight - renderedHeight
        : (plotHeight - renderedHeight) / 2;
    return {
      x: offsetX + ((Number(viewBoxX) - minX) * scale),
      y: offsetY + ((Number(viewBoxY) - minY) * scale),
      plotWidth,
      plotHeight,
    };
  }

  function _heartbeatProfile({ activeCount = 0, averageCpu = 0 } = {}) {
    const cpuLoad = _clampNumber(averageCpu / 100, 0, 1);
    const runLoad = _clampNumber(activeCount * 0.12, 0, 0.45);
    const load = _clampNumber(cpuLoad + runLoad, 0, 1);
    return {
      beatIntervalMs: activeCount ? Math.max(620, 2400 - (load * 1320)) : 2800,
      spike: activeCount ? 13 + (load * 25) : 10,
      recovery: 4 + (load * 6),
      glowOpacity: 0.42 + (load * 0.26),
      glowWidth: 10 + (load * 7),
      beatGlowOpacity: activeCount ? 0.5 + (load * 0.3) : 0.26,
      beatGlowWidth: 16 + (load * 12),
      lineWidth: 1.8 + (load * 0.8),
    };
  }

  function _pulseBucketedCpu(activeCount, averageCpu, hasCpuSample) {
    const resolvedAverage = _clampNumber(averageCpu, 0, 100);
    if (!activeCount || !hasCpuSample) {
      pulseBucketedActiveCount = activeCount;
      pulseBucketedAverageCpu = 0;
      return 0;
    }
    if (
      pulseBucketedAverageCpu === null
      || pulseBucketedActiveCount !== activeCount
      || Math.abs(resolvedAverage - pulseBucketedAverageCpu) > PULSE_CPU_BUCKET_HYSTERESIS
    ) {
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
    const parsed = Date.parse(String(value || ''));
    if (!Number.isFinite(parsed)) return 'time unavailable';
    return new Date(parsed).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  }

  function _parseIsoDateOnly(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || '').trim());
    if (!match) return null;
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const timestamp = Date.UTC(year, month - 1, day);
    return Number.isFinite(timestamp) ? timestamp : null;
  }

  function _formatIsoDateOnly(timestamp) {
    return new Date(timestamp).toISOString().slice(0, 10);
  }

  function _isoWeekdayRow(timestamp) {
    const day = new Date(timestamp).getUTCDay();
    return day === 0 ? 7 : day;
  }

  function _heatmapCalendarDays(activityDays, firstRunDate) {
    const sourceDays = (Array.isArray(activityDays) ? activityDays : [])
      .filter(day => _parseIsoDateOnly(day?.date) !== null);
    if (!sourceDays.length) {
      return { cells: [], weekCount: 0 };
    }
    const firstSource = _parseIsoDateOnly(sourceDays[0].date);
    const lastSource = _parseIsoDateOnly(sourceDays[sourceDays.length - 1].date);
    if (firstSource === null || lastSource === null) {
      return { cells: [], weekCount: 0 };
    }
    const leadingDays = _isoWeekdayRow(firstSource) - 1;
    const gridStart = firstSource - (leadingDays * DAY_MS);
    const totalSourceDays = Math.max(1, Math.round((lastSource - firstSource) / DAY_MS) + 1);
    const weekCount = Math.max(4, Math.ceil((leadingDays + totalSourceDays) / 7));
    const byDate = new Map(sourceDays.map(day => [String(day.date), day]));
    const firstRun = _parseIsoDateOnly(firstRunDate);
    const cells = [];
    for (let index = 0; index < weekCount * 7; index += 1) {
      const timestamp = gridStart + (index * DAY_MS);
      const date = _formatIsoDateOnly(timestamp);
      const source = byDate.get(date);
      const inSourceWindow = timestamp >= firstSource && timestamp <= lastSource;
      cells.push({
        ...(source || { date, count: 0, succeeded: 0, failed: 0, incomplete: 0 }),
        date,
        column: Math.floor(index / 7) + 1,
        row: (index % 7) + 1,
        inSourceWindow,
        outOfRange: !inSourceWindow || firstRun === null || timestamp < firstRun,
      });
    }
    return { cells, weekCount };
  }

  function _monthShortLabel(date) {
    const timestamp = _parseIsoDateOnly(date);
    if (timestamp === null) return '';
    return new Date(timestamp).toLocaleString(undefined, {
      month: 'short',
      timeZone: 'UTC',
    });
  }

  function _heatmapMonthMarkers(calendar) {
    const seenMonths = new Set();
    return (calendar?.cells || []).reduce((markers, day) => {
      if (!day?.inSourceWindow) return markers;
      const monthKey = String(day.date || '').slice(0, 7);
      if (seenMonths.has(monthKey)) return markers;
      const dayOfMonth = String(day.date || '').slice(8, 10);
      if (dayOfMonth !== '01' && markers.length) return markers;
      seenMonths.add(monthKey);
      markers.push({ label: _monthShortLabel(day.date), column: day.column });
      return markers;
    }, []);
  }

  function _heatmapPopoverText(day) {
    const count = Number(day?.count || 0);
    return {
      root: String(day?.date || 'day'),
      command: `${_formatCount(count)} ${count === 1 ? 'run' : 'runs'}`,
      success: `${_formatCount(day?.succeeded || 0)} success`,
      fail: `${_formatCount(day?.failed || 0)} fail`,
      incomplete: `${_formatCount(day?.incomplete || 0)} incomplete`,
      range: day?.outOfRange ? 'outside range' : 'in range',
    };
  }

  function _showHeatmapPopover(panel, day, cell, event = null) {
    const popover = panel.querySelector('.status-monitor-constellation-popover');
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
    const hasPointer = event
      && Number.isFinite(Number(event.clientX))
      && Number.isFinite(Number(event.clientY));
    const targetX = hasPointer
      ? Number(event.clientX) - Number(plotRect.left || 0)
      : (Number(cellRect.left) - Number(plotRect.left || 0)) + (Number(cellRect.width) / 2);
    const targetY = hasPointer
      ? Number(event.clientY) - Number(plotRect.top || 0)
      : (Number(cellRect.top) - Number(plotRect.top || 0)) + (Number(cellRect.height) / 2);
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
    const preferredTop = targetY - (popoverHeight / 2);
    const top = _clampNumber(preferredTop, margin, maxTop);
    popover.style.left = `${left.toFixed(1)}px`;
    popover.style.top = `${top.toFixed(1)}px`;
    popover.classList.toggle('status-monitor-constellation-popover-below', false);
    popover.classList.add('status-monitor-constellation-popover-visible');
    popover.setAttribute('aria-hidden', 'false');
  }

  function _formatPercent(value) {
    if (!_isTelemetryNumber(value)) return '0%';
    const number = Math.max(0, Math.min(100, Number(value)));
    return `${number.toFixed(number >= 10 ? 0 : 1)}%`;
  }

  function _statusLabel(value) {
    const normalized = String(value || '').trim().toLowerCase();
    if (normalized === 'ok') return 'online';
    if (normalized === 'down') return 'down';
    if (normalized === 'none') return 'not configured';
    return normalized || 'unknown';
  }

  function _statusTone(value) {
    const normalized = String(value || '').trim().toLowerCase();
    if (normalized === 'ok') return 'ok';
    if (normalized === 'none') return 'idle';
    if (normalized === 'down') return 'bad';
    return 'warn';
  }

  function _memoryPercent(value) {
    if (!_isTelemetryNumber(value)) return null;
    const gibibyte = 1024 * 1024 * 1024;
    return Math.min(100, Math.max(0, (Number(value) / gibibyte) * 100));
  }

  function _meterPercent(value) {
    if (!_isTelemetryNumber(value)) return 0;
    return Math.min(100, Math.max(0, Number(value)));
  }

  function _statusMonitorMeter({ label, value, percent, className = '', collecting = false, ariaValue = value }) {
    const meter = document.createElement('div');
    meter.className = `status-monitor-meter ${className} ${collecting ? 'status-monitor-meter-collecting' : ''}`.trim();
    meter.style.setProperty('--meter-percent', `${collecting ? 75 : _meterPercent(percent)}%`);
    meter.setAttribute('aria-label', `${label} ${ariaValue}`);

    const labelEl = document.createElement('span');
    labelEl.className = 'status-monitor-meter-label';
    labelEl.textContent = label;

    const ring = document.createElement('span');
    ring.className = 'status-monitor-meter-ring';

    const valueEl = document.createElement('span');
    valueEl.className = 'status-monitor-meter-value';
    valueEl.textContent = value;

    ring.append(valueEl);
    meter.append(labelEl, ring);
    return meter;
  }

  function _updateStatusMonitorMeter(meter, { label, value, percent, collecting = false, ariaValue = value }) {
    meter.classList.toggle('status-monitor-meter-collecting', collecting);
    const nextPercent = `${collecting ? 75 : _meterPercent(percent)}%`;
    if (meter.style.getPropertyValue('--meter-percent') !== nextPercent) {
      meter.style.setProperty('--meter-percent', nextPercent);
    }
    const ariaLabel = `${label} ${ariaValue}`;
    if (meter.getAttribute('aria-label') !== ariaLabel) {
      meter.setAttribute('aria-label', ariaLabel);
    }
    const valueEl = meter.querySelector('.status-monitor-meter-value');
    if (valueEl && valueEl.textContent !== String(value)) {
      valueEl.textContent = String(value);
    }
  }

  function _tabForRun(run) {
    const runId = String(run?.run_id || run?.id || '');
    const currentTabs = typeof getTabs === 'function' ? getTabs() : [];
    if (!runId || !Array.isArray(currentTabs)) return null;
    return currentTabs.find(candidate => (
      candidate && (candidate.runId === runId || candidate.historyRunId === runId)
    )) || null;
  }

  function _isPtyRun(run) {
    return String(run?.run_type || '').toLowerCase() === 'pty';
  }

  function _ptyAttachUnavailableMessage(run) {
    if (!_isPtyRun(run) || _tabForRun(run)) return '';
    if (run?.has_live_owner && !run?.owned_by_this_client) {
      return 'Interactive PTY is still running in another browser. Return to the owning browser tab for the live terminal, or use Kill here if it should stop.';
    }
    if (run?.owner_stale) {
      return 'Interactive PTY is still running, but this browser cannot reconstruct the terminal after reload yet. Status Monitor can track or kill it until saved output lands.';
    }
    return 'Interactive PTY is still running. Live reattach from Status Monitor is not available yet; use the owning tab while it remains open.';
  }

  function _tabLabelForRun(run) {
    const tab = _tabForRun(run);
    if (!tab) return '';
    return String(tab.label || tab.command || tab.id || '').trim();
  }

  function _statusMonitorActionButton(label, title, onClick, options = {}) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn-secondary btn-compact status-monitor-action-btn';
    if (options.className) btn.classList.add(...String(options.className).split(/\s+/).filter(Boolean));
    btn.textContent = label;
    btn.title = title;
    btn.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      const result = onClick();
      Promise.resolve(result).then(attached => {
        if (attached && options.closeOnSuccess !== false) closeStatusMonitor();
      }).catch(err => {
        if (typeof showToast === 'function') {
          showToast(err?.message || 'Could not complete run action', 'error');
        }
      });
    });
    return btn;
  }

  function _openHistoryForCommandRoot(root) {
    const commandRoot = String(root || '').trim();
    if (!commandRoot) return false;
    if (typeof window.openHistoryWithFilters !== 'function') {
      if (typeof showToast === 'function') showToast('History filtering is not available', 'error');
      return false;
    }
    window.openHistoryWithFilters({ type: 'runs', commandRoot });
    closeStatusMonitor();
    return true;
  }

  function _restoreConstellationRun(star) {
    const runId = String(star?.id || '').trim();
    if (!runId) return Promise.resolve(false);
    if (typeof window.restoreHistoryRun !== 'function') {
      if (typeof showToast === 'function') showToast('Run restore is not available', 'error');
      return Promise.resolve(false);
    }
    return Promise.resolve(window.restoreHistoryRun(runId, { hidePanelOnSuccess: false }))
      .then(() => {
        closeStatusMonitor();
        return true;
      })
      .catch(err => {
        if (typeof showToast === 'function') {
          showToast(err?.message || 'Failed to restore run', 'error');
        }
        return false;
      });
  }

  function _clearDocumentSelection() {
    const selection = window.getSelection?.();
    if (selection && typeof selection.removeAllRanges === 'function') {
      selection.removeAllRanges();
    }
  }

  function _positionMonitor() {
    const rail = document.getElementById('rail');
    const right = rail ? Math.ceil(rail.getBoundingClientRect().right) : 0;
    const hud = document.getElementById('hud');
    const hudBottom = hud ? Math.ceil(window.innerHeight - hud.getBoundingClientRect().top) : 46;
    document.documentElement.style.setProperty('--status-monitor-left', `${right}px`);
    document.documentElement.style.setProperty('--status-monitor-bottom', `${hudBottom}px`);
  }

  function _updateElapsedTimers() {
    document.querySelectorAll('[data-status-monitor-started]').forEach(el => {
      el.textContent = _formatElapsed(el.getAttribute('data-status-monitor-started'));
    });
  }

  function _updateLiveUptimeDisplays() {
    const uptime = _statusMonitorUptimeText();
    document.querySelectorAll('[data-status-monitor-uptime-value]').forEach(el => {
      if (el.textContent !== uptime) el.textContent = uptime;
    });
    const prefix = summaryEl?.dataset?.statusMonitorSummaryPrefix;
    if (summaryEl && prefix) {
      const text = `${prefix} · ${uptime} uptime`;
      if (summaryEl.textContent !== text) summaryEl.textContent = text;
    }
  }

  async function _loadActiveRuns() {
    const resp = await apiFetch('/history/active');
    const data = await resp.json();
    if (!resp.ok) throw new Error(data?.error || `HTTP ${resp.status}`);
    return Array.isArray(data?.runs) ? data.runs : [];
  }

  async function _loadSystemStatus() {
    const startedAt = Date.now();
    const resp = await apiFetch('/status');
    const data = await resp.json();
    if (!resp.ok) throw new Error(data?.error || `HTTP ${resp.status}`);
    const payload = data && typeof data === 'object' ? data : {};
    payload.latency_ms = Date.now() - startedAt;
    payload.uptime_received_at_ms = Date.now();
    return payload;
  }

  async function _loadWorkspaceStatus() {
    const resp = await apiFetch('/workspace/files');
    const data = await resp.json();
    if (!resp.ok) return { enabled: false, error: data?.error || `HTTP ${resp.status}` };
    return data && typeof data === 'object' ? data : {};
  }

  async function _loadSessionStats() {
    const resp = await apiFetch('/history/stats');
    const data = await resp.json();
    if (!resp.ok) throw new Error(data?.error || `HTTP ${resp.status}`);
    return data && typeof data === 'object' ? data : {};
  }

  async function _loadHistoryInsights() {
    const resp = await apiFetch('/history/insights');
    const data = await resp.json();
    if (!resp.ok) throw new Error(data?.error || `HTTP ${resp.status}`);
    return data && typeof data === 'object' ? data : {};
  }

  async function _refreshHistoryInsights() {
    try {
      cachedInsights = await _loadHistoryInsights();
    } catch (err) {
      cachedInsights = { error: err?.message || 'Unavailable' };
    }
    return cachedInsights;
  }

  async function _refreshDashboardData({ includeInsights = false } = {}) {
    const shouldLoadInsights = includeInsights || !cachedInsights;
    const [status, workspace, stats, insights] = await Promise.allSettled([
      _loadSystemStatus(),
      _loadWorkspaceStatus(),
      _loadSessionStats(),
      shouldLoadInsights ? _loadHistoryInsights() : Promise.resolve(cachedInsights),
    ]);
    cachedStatus = status.status === 'fulfilled'
      ? status.value
      : { error: status.reason?.message || 'Unavailable' };
    cachedWorkspace = workspace.status === 'fulfilled'
      ? workspace.value
      : { enabled: false, error: workspace.reason?.message || 'Unavailable' };
    cachedStats = stats.status === 'fulfilled'
      ? stats.value
      : { error: stats.reason?.message || 'Unavailable' };
    if (shouldLoadInsights) cachedInsights = insights.status === 'fulfilled'
      ? insights.value
      : { error: insights.reason?.message || 'Unavailable' };
  }

  async function _refreshActiveRunCache({ render = false, renderWhileOpen = true } = {}) {
    const runs = await _loadActiveRuns();
    cachedRuns = runs;
    runs.forEach(run => _runResourceUsage(run));
    if (render || (renderWhileOpen && isOpen)) _renderDashboard(runs);
    if (!runs.length) {
      resourceStateByRunId.clear();
      _stopClosedPolling();
    }
    return runs;
  }

  function _ensureMonitor() {
    if (monitorEl && scrimEl && listEl && summaryEl) return;

    scrimEl = document.createElement('div');
    scrimEl.className = 'status-monitor-scrim u-hidden';
    scrimEl.setAttribute('aria-hidden', 'true');
    scrimEl.addEventListener('click', () => closeStatusMonitor());

    monitorEl = document.createElement('aside');
    monitorEl.id = 'status-monitor';
    monitorEl.className = 'status-monitor status-monitor-modal chrome-drawer mobile-sheet-surface u-hidden';
    monitorEl.setAttribute('role', 'dialog');
    monitorEl.setAttribute('aria-modal', 'true');
    monitorEl.setAttribute('aria-labelledby', 'status-monitor-title');

    const header = document.createElement('div');
    header.className = 'status-monitor-header surface-header';

    const titleWrap = document.createElement('div');
    const title = document.createElement('div');
    title.id = 'status-monitor-title';
    title.className = 'status-monitor-title';
    title.textContent = 'Status Monitor';
    summaryEl = document.createElement('div');
    summaryEl.className = 'status-monitor-summary';
    summaryEl.textContent = 'Loading...';
    titleWrap.append(title, summaryEl);

    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'status-monitor-close';
    closeBtn.setAttribute('aria-label', 'Close status monitor');
    const closeIcon = document.createElement('span');
    closeIcon.className = 'status-monitor-collapse-glyph';
    closeIcon.setAttribute('aria-hidden', 'true');
    closeIcon.textContent = '✕';
    closeBtn.appendChild(closeIcon);
    closeBtn.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      closeStatusMonitor();
    });

    header.append(titleWrap, closeBtn);

    listEl = document.createElement('div');
    listEl.className = 'status-monitor-list surface-body';

    monitorEl.append(header, listEl);
    monitorEl.addEventListener('click', event => event.stopPropagation());
    document.body.append(scrimEl, monitorEl);
    if (typeof bindFocusTrap === 'function') bindFocusTrap(monitorEl);
    if (typeof bindDismissible === 'function') {
      bindDismissible(monitorEl, {
        level: 'modal',
        isOpen: () => isOpen,
        onClose: () => closeStatusMonitor(),
        backdropEl: scrimEl,
        closeButtons: closeBtn,
      });
    }
    if (typeof bindMobileSheet === 'function') {
      bindMobileSheet(monitorEl, { onClose: () => closeStatusMonitor() });
    }
  }

  function _statusSection(title, meta = '') {
    const section = document.createElement('section');
    section.className = 'status-monitor-section';
    const header = document.createElement('div');
    header.className = 'status-monitor-section-header';
    const titleEl = document.createElement('div');
    titleEl.className = 'status-monitor-section-title';
    titleEl.textContent = title;
    header.appendChild(titleEl);
    if (meta) {
      const metaEl = document.createElement('div');
      metaEl.className = 'status-monitor-section-meta';
      metaEl.textContent = meta;
      header.appendChild(metaEl);
    }
    section.appendChild(header);
    return section;
  }

  function _statusCard({ label, value, meta = '', tone = '', meterPercent = null, compact = false, valueDataset = null }) {
    const card = document.createElement('div');
    card.className = `status-monitor-card ${tone ? `status-monitor-card-${tone}` : ''} ${compact ? 'status-monitor-card-compact' : ''}`.trim();
    const labelEl = document.createElement('div');
    labelEl.className = 'status-monitor-card-label';
    labelEl.textContent = label;
    const valueRow = document.createElement('div');
    valueRow.className = 'status-monitor-card-value-row';
    if (tone) {
      const dot = document.createElement('span');
      dot.className = `status-monitor-dot status-monitor-dot-${tone}`;
      dot.setAttribute('aria-hidden', 'true');
      valueRow.appendChild(dot);
    }
    const valueEl = document.createElement('div');
    valueEl.className = 'status-monitor-card-value';
    valueEl.textContent = value;
    if (valueDataset && typeof valueDataset === 'object') {
      Object.entries(valueDataset).forEach(([key, datasetValue]) => {
        valueEl.dataset[key] = String(datasetValue);
      });
    }
    valueRow.appendChild(valueEl);
    card.append(labelEl, valueRow);
    if (meta) {
      const metaEl = document.createElement('div');
      metaEl.className = 'status-monitor-card-meta';
      metaEl.textContent = meta;
      card.appendChild(metaEl);
    }
    if (_isTelemetryNumber(meterPercent)) {
      const bar = document.createElement('div');
      bar.className = 'status-monitor-card-meter';
      bar.style.setProperty('--status-meter-percent', `${_meterPercent(meterPercent)}%`);
      card.appendChild(bar);
    }
    return card;
  }

  function _statusGrid(cards, className = '') {
    const grid = document.createElement('div');
    grid.className = `status-monitor-grid ${className}`.trim();
    cards.filter(Boolean).forEach(card => grid.appendChild(card));
    return grid;
  }

  function _pulseStripData(runs) {
    const status = cachedStatus || {};
    const activeRuns = Array.isArray(runs) ? runs : [];
    const cpuValues = [];
    activeRuns.forEach((run) => {
      const state = resourceStateByRunId.get(String(run?.run_id || run?.id || ''));
      if (_isTelemetryNumber(state?.cpu_percent)) {
        cpuValues.push(Math.max(0, Number(state.cpu_percent)));
      }
    });
    const avgCpu = cpuValues.length
      ? cpuValues.reduce((total, value) => total + value, 0) / cpuValues.length
      : 0;
    const cpuSamples = _pulseRecentCpuWindow(activeRuns.length, avgCpu, cpuValues.length > 0);
    const signatureCpuBucket = _pulseBucketedCpu(activeRuns.length, avgCpu, cpuValues.length > 0);
    const cpuMeta = activeRuns.length && cpuValues.length
      ? ` · ${_formatCpuPercent(avgCpu)} avg CPU`
      : '';
    const profile = _heartbeatProfile({ activeCount: activeRuns.length, averageCpu: avgCpu });
    const summaryPrefix = `${activeRuns.length} active${cpuMeta}`;
    return {
      signature: `${activeRuns.length}:${signatureCpuBucket}`,
      activeCount: activeRuns.length,
      averageCpu: avgCpu,
      cpuSamples,
      ...profile,
      summaryPrefix,
      meta: `${summaryPrefix} · ${_statusMonitorUptimeText(status)} uptime`,
    };
  }

  function _pulseLoadTier(averageCpu, hasCpuSample, activeCount) {
    if (!activeCount || !hasCpuSample) {
      return {
        name: 'idle',
        color: 'var(--green)',
        alpha: 0.1,
        borderAlpha: 0.28,
        shadowAlpha: 0.08,
      };
    }
    const cpu = _clampNumber(averageCpu, 0, 100);
    if (cpu >= 85) {
      return {
        name: 'very-heavy',
        color: 'var(--red)',
        alpha: 0.34,
        borderAlpha: 0.58,
        shadowAlpha: 0.2,
      };
    }
    if (cpu >= 65) {
      return {
        name: 'heavy',
        color: 'var(--orange, #ff7a18)',
        alpha: 0.3,
        borderAlpha: 0.52,
        shadowAlpha: 0.18,
      };
    }
    if (cpu >= 35) {
      return {
        name: 'busy',
        color: 'var(--amber)',
        alpha: 0.24,
        borderAlpha: 0.45,
        shadowAlpha: 0.15,
      };
    }
    return {
      name: 'light',
      color: 'var(--green)',
      alpha: 0.16,
      borderAlpha: 0.34,
      shadowAlpha: 0.1,
    };
  }

  function _applyPulseLoadStyle(strip, data) {
    if (!strip) return;
    const hasCpuSample = Array.isArray(data?.cpuSamples) && data.cpuSamples.length > 0;
    const tier = suppressPulseLoadUntilFresh
      ? _pulseLoadTier(0, false, 0)
      : _pulseLoadTier(data?.averageCpu || 0, hasCpuSample, data?.activeCount || 0);
    strip.dataset.pulseLoad = tier.name;
    strip.style.setProperty('--pulse-load-color', tier.color);
    strip.style.setProperty('--pulse-load-alpha', tier.alpha.toFixed(2));
    strip.style.setProperty('--pulse-load-border-alpha', tier.borderAlpha.toFixed(2));
    strip.style.setProperty('--pulse-load-shadow-alpha', tier.shadowAlpha.toFixed(2));
  }

  function _pulseBeatPoints(beat) {
    const baseline = PULSE_BASELINE_Y;
    const x = beat.x;
    return [
      [x - 8, baseline],
      [x - 1, baseline],
      [x + 3, baseline + beat.recovery],
      [x + 8, baseline - beat.spike],
      [x + 13, baseline + (beat.spike * 0.56)],
      [x + 19, baseline],
      [x + 25, baseline - (beat.recovery * 0.72)],
      [x + 34, baseline],
    ];
  }

  function _visiblePulseBeats(beats, offset = 0) {
    return beats
      .filter(beat => {
        const renderedX = beat.x - offset;
        return renderedX > -70 && renderedX < PULSE_VIEW_WIDTH + 70;
      })
      .sort((left, right) => left.x - right.x);
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
    const pathStart = _isTelemetryNumber(options.pathStart)
      ? Number(options.pathStart)
      : viewportStart - PULSE_PATH_MARGIN;
    const pathEnd = _isTelemetryNumber(options.pathEnd)
      ? Number(options.pathEnd)
      : viewportEnd + PULSE_PATH_MARGIN;
    beats.forEach(beat => {
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
    if (pathEnd <= pathStart) return '';
    const width = pathEnd - pathStart;
    const step = Math.max(10, Math.min(20, width / 32));
    const points = [];
    for (let x = pathStart; x < pathEnd; x += step) {
      const progress = (x - pathStart) / width;
      const wave = Math.sin(progress * Math.PI * 8) * Math.sin(progress * Math.PI);
      points.push([x, PULSE_BASELINE_Y + (wave * 1.4)]);
    }
    points.push([pathEnd, PULSE_BASELINE_Y]);
    return _pathFromPoints(points);
  }

  function _pulseBeatGlowPath(beat) {
    return _pathFromPoints(_pulseBeatPoints(beat));
  }

  function _pulseGlowGroups(beats) {
    const groups = new Map();
    beats.forEach((beat) => {
      const key = [
        beat.glowOpacity.toFixed(2),
        beat.glowWidth.toFixed(1),
        beat.beatGlowOpacity.toFixed(2),
        beat.beatGlowWidth.toFixed(1),
      ].join(':');
      const group = groups.get(key) || {
        key,
        glowOpacity: beat.glowOpacity,
        glowWidth: beat.glowWidth,
        beatGlowOpacity: beat.beatGlowOpacity,
        beatGlowWidth: beat.beatGlowWidth,
        paths: [],
      };
      group.paths.push(_pulseBeatGlowPath(beat));
      groups.set(key, group);
    });
    return groups;
  }

  function _syncPulseGlowGroup(groupEl, groups, className, styleFor) {
    if (!groupEl) return;
    const existing = new Map(
      [...groupEl.children].map(child => [child.dataset.pulseGlowKey, child]),
    );
    const seen = new Set();
    groups.forEach((group) => {
      let path = existing.get(group.key);
      if (!path) {
        path = _svgEl('path', { class: className });
        path.dataset.pulseGlowKey = group.key;
        groupEl.appendChild(path);
      }
      path.setAttribute('d', group.paths.join(' '));
      path.setAttribute('style', styleFor(group));
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
        beatGlowMinOpacity: 0,
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
      beatGlowMinOpacity: 0.08,
    };
  }

  function _renderMobilePulseGlowEllipses(groupEl, beats, gradientId) {
    if (!groupEl || !gradientId) return;
    const fragment = document.createDocumentFragment();
    beats.forEach((beat) => {
      const load = _clampNumber((Number(beat.spike || 0) - 10) / 28, 0, 1);
      const points = _pulseBeatPoints(beat);
      const xs = points.map(point => point[0]);
      const ys = points.map(point => point[1]);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      const beatHeight = Math.max(1, maxY - minY);
      const smallBeatBoost = (1 - load) * 8;
      const radius = (beatHeight * 0.62) + 6 + (load * 4) + smallBeatBoost;
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
      const centerY = (weightedCenterY * 0.38) + (PULSE_BASELINE_Y * 0.62);
      const ellipse = _svgEl('ellipse', {
        class: 'status-monitor-pulse-mobile-glow',
        cx: centerX.toFixed(1),
        cy: centerY.toFixed(1),
        rx: radius.toFixed(1),
        ry: (radius * 1.08).toFixed(1),
        opacity: _clampNumber(0.64 + (load * 0.22) + ((1 - load) * 0.04), 0.64, 0.86).toFixed(2),
        fill: `url(#${gradientId})`,
      });
      fragment.appendChild(ellipse);
    });
    groupEl.replaceChildren(fragment);
  }

  function _pulseNodes(strip) {
    let nodes = pulseNodeCacheByStrip.get(strip);
    if (!nodes) {
      nodes = {
        track: strip.querySelector('.status-monitor-pulse-track'),
        broadGroup: strip.querySelector('.status-monitor-pulse-glows'),
        beatGroup: strip.querySelector('.status-monitor-pulse-beat-glows'),
        placeholderLine: strip.querySelector('.status-monitor-pulse-placeholder-line'),
        line: strip.querySelector('.status-monitor-pulse-line'),
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
      _renderMobilePulseGlowEllipses(broadGroup, beats, strip.dataset.pulseGlowGradientId || '');
    } else {
      _syncPulseGlowGroup(broadGroup, groups, 'status-monitor-pulse-glow', group => [
        `--pulse-glow-opacity:${Math.max(scale.glowMinOpacity, group.glowOpacity * scale.glowOpacity).toFixed(2)}`,
        `--pulse-glow-width:${Math.max(scale.glowMinWidth, group.glowWidth * scale.glowWidth).toFixed(1)}px`,
      ].join(';'));
    }
    _syncPulseGlowGroup(beatGroup, groups, 'status-monitor-pulse-beat-glow', group => [
      `--pulse-beat-glow-opacity:${Math.max(scale.beatGlowMinOpacity, group.beatGlowOpacity * scale.beatGlowOpacity).toFixed(2)}`,
      `--pulse-beat-glow-width:${Math.max(scale.beatGlowMinWidth, group.beatGlowWidth * scale.beatGlowWidth).toFixed(1)}px`,
    ].join(';'));
  }

  function _pulseBeatFromData(x, data, index = 0) {
    const cpuSamples = Array.isArray(data.cpuSamples) && data.cpuSamples.length
      ? data.cpuSamples
      : [data.averageCpu || 0];
    const sampleCpu = cpuSamples[Math.abs(index) % cpuSamples.length];
    const profile = _heartbeatProfile({ activeCount: data.activeCount, averageCpu: sampleCpu });
    return {
      x,
      spike: profile.spike,
      recovery: profile.recovery,
      glowOpacity: profile.glowOpacity,
      glowWidth: profile.glowWidth,
      beatGlowOpacity: profile.beatGlowOpacity,
      beatGlowWidth: profile.beatGlowWidth,
    };
  }

  function _pulseNow() {
    return window.performance && typeof window.performance.now === 'function'
      ? window.performance.now()
      : Date.now();
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
      signature: data.signature,
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
    document.querySelectorAll('.status-monitor-pulse-strip').forEach(strip => {
      strip.classList.add('status-monitor-pulse-load-resetting');
      pulseStateByStrip.delete(strip);
      const nodes = _pulseNodes(strip);
      nodes.placeholderLine?.setAttribute('d', '');
      nodes.line?.setAttribute('d', '');
      nodes.broadGroup?.replaceChildren();
      nodes.beatGroup?.replaceChildren();
      nodes.track?.setAttribute('transform', 'translate(0 0)');
      strip.dataset.pulseLoad = idleTier.name;
      strip.style.setProperty('--pulse-load-color', idleTier.color);
      strip.style.setProperty('--pulse-load-alpha', idleTier.alpha.toFixed(2));
      strip.style.setProperty('--pulse-load-border-alpha', idleTier.borderAlpha.toFixed(2));
      strip.style.setProperty('--pulse-load-shadow-alpha', idleTier.shadowAlpha.toFixed(2));
      void strip.offsetWidth;
      strip.classList.remove('status-monitor-pulse-load-resetting');
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
          state.beatCursor || 0,
        ));
        state.beatCursor = (state.beatCursor || 0) + 1;
        state.nextBeatInMs += state.latestProfile.beatIntervalMs;
        state.geometryDirty = true;
      }
      const remainingBeats = state.beats.filter(beat => (beat.x - (state.offset || 0)) > -76);
      if (remainingBeats.length !== state.beats.length) {
        state.beats = remainingBeats;
        state.geometryDirty = true;
      }
    }

    const offset = state.offset || 0;
    if (state.geometryDirty) {
      const renderableBeats = _renderablePulseBeats(state.beats, offset);
      const liveStartX = _isTelemetryNumber(state.liveStartX)
        ? Number(state.liveStartX)
        : offset - PULSE_PATH_MARGIN;
      const placeholderEnd = Math.min(liveStartX, offset + PULSE_VIEW_WIDTH + PULSE_PATH_MARGIN);
      const placeholderPath = placeholderEnd > offset - PULSE_PATH_MARGIN
        ? _pulsePlaceholderPath(offset - PULSE_PATH_MARGIN, placeholderEnd)
        : '';
      const path = _pulsePathFromBeats(renderableBeats, offset, offset + PULSE_VIEW_WIDTH, {
        pathStart: Math.max(liveStartX, offset - PULSE_PATH_MARGIN),
        pathEnd: offset + PULSE_VIEW_WIDTH + PULSE_PATH_MARGIN,
      });
      _renderPulseBeatGlows(strip, renderableBeats);
      nodes.placeholderLine?.setAttribute('d', placeholderPath);
      nodes.line?.setAttribute('d', path);
      state.geometryDirty = false;
    }
    nodes.track?.setAttribute('transform', `translate(${-offset.toFixed(1)} 0)`);
  }

  function _renderPulseStrips(timestamp) {
    document.querySelectorAll('.status-monitor-pulse-strip').forEach(strip => {
      _renderPulseState(strip, timestamp);
    });
  }

  function _pulseMotionReduced() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  function _requestPulseFrame(callback) {
    if (typeof window.requestAnimationFrame === 'function') {
      return { type: 'raf', id: window.requestAnimationFrame(callback) };
    }
    return { type: 'timer', id: window.setTimeout(() => callback(_pulseNow()), 16) };
  }

  function _cancelPulseFrame(handle) {
    if (!handle) return;
    if (handle.type === 'raf' && typeof window.cancelAnimationFrame === 'function') {
      window.cancelAnimationFrame(handle.id);
      return;
    }
    window.clearTimeout(handle.id);
  }

  function _startPulseAnimation() {
    if (pulseAnimationFrame || _pulseMotionReduced()) return;
    const frame = (timestamp) => {
      pulseAnimationFrame = null;
      if (!isOpen || document.visibilityState !== 'visible') return;
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
    strip.classList.toggle('status-monitor-pulse-active', data.activeCount > 0);
    strip.dataset.pulseSignature = data.signature;
    strip.dataset.pulseCpuSamples = data.cpuSamples.map(value => Math.round(value).toString()).join(',');
    _applyPulseLoadStyle(strip, data);
    _ensurePulseState(strip, data);
    _renderPulseState(strip, _pulseNow());
  }

  function _renderPulseStrip(runs) {
    const data = _pulseStripData(runs);
    latestPulseData = data;

    const strip = document.createElement('section');
    strip.className = 'status-monitor-pulse-strip';
    strip.classList.toggle('status-monitor-pulse-active', data.activeCount > 0);
    strip.dataset.pulseSignature = data.signature;
    strip.dataset.pulseCpuSamples = data.cpuSamples.map(value => Math.round(value).toString()).join(',');
    strip.dataset.pulseGlowGradientId = `status-monitor-pulse-mobile-glow-${Math.random().toString(36).slice(2)}`;
    _applyPulseLoadStyle(strip, data);
    // On narrow mobile viewports the strip is roughly half as wide as desktop.
    // With `preserveAspectRatio: 'none'` the path geometry compresses
    // horizontally, so beats sit too close together and full-amplitude
    // ECG spikes stack into a wall of overlapping vertical strokes. Use
    // `xMidYMid slice` on mobile so beats render at their native aspect
    // (Y-fill scale ≈ 1.0 with the 720×76 viewBox) and the canvas crops
    // the horizontal overflow — fewer beats are visible at once but each
    // one keeps the same character as desktop.
    const sliceAspect = typeof window.matchMedia === 'function'
      && window.matchMedia('(max-width: 600px)').matches;
    const svg = _svgEl('svg', {
      viewBox: '0 0 720 76',
      preserveAspectRatio: sliceAspect ? 'xMidYMid slice' : 'none',
      class: 'status-monitor-pulse-svg',
      'aria-hidden': 'true',
    });
    const defs = _svgEl('defs');
    const glowGradient = _svgEl('radialGradient', {
      id: strip.dataset.pulseGlowGradientId,
      cx: '50%',
      cy: '50%',
      r: '50%',
      fx: '50%',
      fy: '50%',
    });
    glowGradient.append(
      _svgEl('stop', { offset: '0%', 'stop-color': 'var(--green)', 'stop-opacity': '1' }),
      _svgEl('stop', { offset: '22%', 'stop-color': 'var(--green)', 'stop-opacity': '0.82' }),
      _svgEl('stop', { offset: '56%', 'stop-color': 'var(--green)', 'stop-opacity': '0.34' }),
      _svgEl('stop', { offset: '84%', 'stop-color': 'var(--green)', 'stop-opacity': '0.08' }),
      _svgEl('stop', { offset: '100%', 'stop-color': 'var(--green)', 'stop-opacity': '0' }),
    );
    defs.appendChild(glowGradient);
    const track = _svgEl('g', { class: 'status-monitor-pulse-track' });
    track.append(
      _svgEl('g', { class: 'status-monitor-pulse-glows' }),
      _svgEl('g', { class: 'status-monitor-pulse-beat-glows' }),
      _svgEl('path', { class: 'status-monitor-pulse-placeholder-line', d: '' }),
      _svgEl('path', { class: 'status-monitor-pulse-line', d: '' }),
    );
    svg.append(
      defs,
      _svgEl('path', { class: 'status-monitor-pulse-grid', d: 'M0 40 L720 40' }),
      track,
    );

    strip.append(svg);
    _ensurePulseState(strip, data);
    _renderPulseState(strip, _pulseNow());
    return strip;
  }

  function _constellationPopover() {
    const popover = document.createElement('div');
    popover.className = 'status-monitor-constellation-popover';
    popover.setAttribute('aria-hidden', 'true');

    const root = document.createElement('div');
    root.className = 'status-monitor-constellation-popover-root';
    root.dataset.field = 'root';
    const command = document.createElement('div');
    command.className = 'status-monitor-constellation-popover-command';
    command.dataset.field = 'command';
    const meta = document.createElement('div');
    meta.className = 'status-monitor-constellation-popover-meta';
    ['time', 'duration', 'exit', 'lines'].forEach((field) => {
      const item = document.createElement('span');
      item.dataset.field = field;
      meta.appendChild(item);
    });
    popover.append(root, command, meta);
    return popover;
  }

  function _constellationPopoverKey(star) {
    return String(star?.id || star?.command || star?.root || '').trim().toLowerCase();
  }

  function _clearConstellationPopoverTimer(panel) {
    const timer = constellationPopoverTimerByPanel.get(panel);
    if (timer) {
      window.clearTimeout(timer);
      constellationPopoverTimerByPanel.delete(panel);
    }
  }

  function _showConstellationPopover(panel, star, x, y) {
    const popover = panel.querySelector('.status-monitor-constellation-popover');
    if (!popover) return;
    _clearConstellationPopoverTimer(panel);
    panel.dataset.constellationPopoverStar = _constellationPopoverKey(star);
    const plot = popover.parentElement;
    const root = String(star.root || 'run');
    const category = String(star.category || 'Other');
    const exitCode = _exitCodeLabel(star.exit_code);
    popover.querySelector('[data-field="root"]').textContent = `${root} · ${category}`;
    popover.querySelector('[data-field="command"]').textContent = _truncateText(star.command || root, 92);
    popover.querySelector('[data-field="time"]').textContent = _formatStarStarted(star.started);
    popover.querySelector('[data-field="duration"]').textContent = _formatDurationSeconds(star.elapsed_seconds);
    popover.querySelector('[data-field="exit"]').textContent = exitCode;
    popover.querySelector('[data-field="lines"]').textContent = `${_formatCount(star.output_line_count || 0)} lines`;
    const svg = plot?.querySelector?.('.status-monitor-constellation');
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
    const left = _clampNumber(targetX - (popoverWidth / 2), margin, maxLeft);
    const preferredTop = below ? targetY + gap : targetY - popoverHeight - gap;
    const top = _clampNumber(preferredTop, margin, maxTop);
    popover.style.left = `${left.toFixed(1)}px`;
    popover.style.top = `${top.toFixed(1)}px`;
    popover.classList.toggle('status-monitor-constellation-popover-below', below);
    popover.classList.add('status-monitor-constellation-popover-visible');
    popover.setAttribute('aria-hidden', 'false');
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
    const popover = panel.querySelector('.status-monitor-constellation-popover');
    if (!popover) return;
    _clearConstellationPopoverTimer(panel);
    delete panel.dataset.constellationPopoverStar;
    popover.classList.remove('status-monitor-constellation-popover-visible', 'status-monitor-constellation-popover-below');
    popover.setAttribute('aria-hidden', 'true');
  }

  function _constellationSparseMessage(starCount) {
    const count = Number(starCount || 0);
    if (count <= 0) return 'Run history will populate this constellation.';
    if (count < 5) return 'More runs will sharpen this map.';
    return '';
  }

  function _splitConstellationStreakSegments(group) {
    // Streaks already group same-root points (e.g. nuclei connects to nuclei
    // only). Add max ≤2h between consecutive starts AND same calendar date so
    // a long-running session at 23:30 → 00:30 splits at midnight rather than
    // wrapping back across the entire X axis, and bursts hours apart are not
    // joined into spaghetti.
    const TWO_HOURS_MS = 2 * 60 * 60 * 1000;
    const segments = [];
    let current = [];
    let previous = null;
    for (const point of group) {
      if (previous) {
        const sameDay = new Date(previous.started).toDateString()
          === new Date(point.started).toDateString();
        const within2h = (point.started - previous.started) <= TWO_HOURS_MS;
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
    if (!Array.isArray(points) || points.length < 2) return '';
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
    return commands.join(' ');
  }

  function _constellationTimeGuideX(hour) {
    return CONSTELLATION_PLOT_LEFT + ((hour * 60) / 1440) * CONSTELLATION_PLOT_WIDTH;
  }

  function _formatConstellationAxisDuration(seconds) {
    const total = Math.max(0, Number(seconds) || 0);
    if (total < 1) return '0s';
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
      { fraction: 1, major: true },
    ];
    for (const { fraction, major } of ticks) {
      const y = CONSTELLATION_Y_BASELINE - (fraction * CONSTELLATION_Y_RANGE);
      svg.appendChild(_svgEl('line', {
        class: major
          ? 'status-monitor-constellation-guide status-monitor-constellation-guide-major'
          : 'status-monitor-constellation-guide status-monitor-constellation-guide-minor',
        x1: CONSTELLATION_PLOT_LEFT,
        y1: y,
        x2: CONSTELLATION_PLOT_RIGHT,
        y2: y,
      }));
      const seconds = Math.expm1(fraction * logCeil);
      const label = _svgEl('text', {
        class: 'status-monitor-constellation-guide-label status-monitor-constellation-guide-label-y',
        x: CONSTELLATION_PLOT_LEFT - 6,
        y,
        'text-anchor': 'end',
      });
      label.textContent = _formatConstellationAxisDuration(seconds);
      svg.appendChild(label);
    }
  }

  function _appendConstellationTimeGuides(svg) {
    for (let hour = 0; hour <= 24; hour += 2) {
      if (hour % 4 === 0) continue;
      const x = _constellationTimeGuideX(hour);
      svg.appendChild(_svgEl('line', {
        class: 'status-monitor-constellation-guide status-monitor-constellation-guide-minor',
        x1: x,
        y1: 12,
        x2: x,
        y2: 286,
      }));
    }
    for (let hour = 0; hour <= 24; hour += 4) {
      const x = _constellationTimeGuideX(hour);
      svg.appendChild(_svgEl('line', {
        class: 'status-monitor-constellation-guide status-monitor-constellation-guide-major',
        x1: x,
        y1: 12,
        x2: x,
        y2: 286,
      }));
      // Stars max out at minute 1439 (23:59), so the `24` tick can never
      // carry data — drop the label so the rightmost cluster reads as
      // 20:00–midnight rather than as overflow at the next-day boundary.
      if (hour === 24) continue;
      const label = _svgEl('text', {
        class: 'status-monitor-constellation-guide-label',
        x: Math.max(CONSTELLATION_PLOT_LEFT, Math.min(CONSTELLATION_PLOT_RIGHT + 4, x)),
        y: 289,
        'text-anchor': 'middle',
      });
      label.textContent = String(hour).padStart(2, '0');
      svg.appendChild(label);
    }
  }

  function _syncConstellationAspect(svg) {
    const rect = svg?.getBoundingClientRect?.();
    const width = Number(rect?.width || 0);
    const height = Number(rect?.height || 0);
    if (width <= 0 || height <= 0) return;
    const xScale = width / 640;
    const yScale = height / 300;
    const starScaleX = xScale > 0 && yScale > 0
      ? _clampNumber(yScale / xScale, 0.34, 1.4)
      : 1;
    svg.style.setProperty('--constellation-star-scale-x', starScaleX.toFixed(3));
  }

  function _scheduleConstellationAspectSync(svg) {
    _syncConstellationAspect(svg);
    if (typeof window.requestAnimationFrame === 'function') {
      window.requestAnimationFrame(() => _syncConstellationAspect(svg));
    }
  }

  function _computeConstellationCeiling(elapsedValues) {
    // p98 + 6% headroom, quantised up to the nearest 10% of full range,
    // floored at 25% of full range. Y in the constellation is log-scaled
    // elapsed_seconds; using p98 as the denominator instead of max() pulls
    // the bulk of stars off the baseline when a single long-tail outlier
    // would otherwise flatten the canvas.
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
    const panel = document.createElement('section');
    panel.className = 'status-monitor-visual-card status-monitor-constellation-card';

    const header = document.createElement('div');
    header.className = 'status-monitor-visual-header';
    const title = document.createElement('div');
    title.className = 'status-monitor-visual-title';
    title.textContent = 'Command Constellation';
    const meta = document.createElement('div');
    meta.className = 'status-monitor-visual-meta';
    meta.textContent = stars.length
      ? `${_formatCount(stars.length)} plotted · ${_insightWindowLabel('constellation', 30)}`
      : `awaiting run history · ${_insightWindowLabel('constellation', 30)}`;
    const legend = _categoryLegend(stars);
    if (legend && stars.length) {
      const hasFailed = stars.some(star => _isFailedExitCode(star?.exit_code));
      if (hasFailed) {
        legend.appendChild(_buildConstellationLegendKey({
          modifier: 'failed',
          ariaLabel: 'Failed runs are ringed in red',
          label: 'Failed',
        }));
      }
      legend.appendChild(_buildConstellationLegendKey({
        modifier: 'size',
        ariaLabel: 'Star size encodes output line count',
        label: 'Output',
      }));
    }
    header.append(title);
    if (legend) header.appendChild(legend);
    header.appendChild(meta);

    const plot = document.createElement('div');
    plot.className = 'status-monitor-constellation-plot';
    plot.addEventListener('pointerleave', () => _hideConstellationPopover(panel));
    plot.addEventListener('focusout', event => {
      if (!plot.contains(event.relatedTarget)) _hideConstellationPopover(panel);
    });

    const svg = _svgEl('svg', {
      class: 'status-monitor-constellation',
      viewBox: '0 0 640 300',
      role: 'img',
      'aria-label': 'Recent command constellation',
      preserveAspectRatio: 'none',
    });
    const starsByNodeId = new Map();
    const starPayloadFromEvent = (event) => {
      const target = event.target;
      const node = target && typeof target.closest === 'function'
        ? target.closest('.status-monitor-star-node')
        : null;
      if (!node || !svg.contains(node)) return null;
      return starsByNodeId.get(node.dataset.starId || '');
    };
    svg.addEventListener('pointerover', event => {
      const payload = starPayloadFromEvent(event);
      if (payload) _showConstellationPopover(panel, payload.star, payload.x, payload.y);
    });
    svg.addEventListener('pointermove', event => {
      const payload = starPayloadFromEvent(event);
      if (payload) _scheduleConstellationPopover(panel, payload.star, payload.x, payload.y);
    });
    svg.addEventListener('focusin', event => {
      const payload = starPayloadFromEvent(event);
      if (payload) _showConstellationPopover(panel, payload.star, payload.x, payload.y);
    });
    svg.addEventListener('click', event => {
      const payload = starPayloadFromEvent(event);
      if (!payload) return;
      event.preventDefault();
      event.stopPropagation();
      _clearDocumentSelection();
      _restoreConstellationRun(payload.star);
    });
    svg.addEventListener('keydown', event => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      const payload = starPayloadFromEvent(event);
      if (!payload) return;
      event.preventDefault();
      event.stopPropagation();
      _clearDocumentSelection();
      _restoreConstellationRun(payload.star);
    });
    const ceilingElapsed = _computeConstellationCeiling(
      stars.map(star => star.elapsed_seconds),
    );
    _appendConstellationTimeGuides(svg);
    _appendConstellationElapsedGuides(svg, ceilingElapsed);
    _ambientConstellationStars().forEach(star => {
      svg.appendChild(_svgEl('circle', {
        class: 'status-monitor-star-ambient',
        cx: star.x,
        cy: star.y,
        r: star.radius,
        style: [
          `--ambient-hue:${star.hue.toFixed(1)}`,
          `--ambient-saturation:${star.saturation.toFixed(1)}%`,
          `--ambient-lightness:${star.lightness.toFixed(1)}%`,
          `--ambient-opacity:${star.opacity.toFixed(2)}`,
          `--ambient-glow:${star.glow.toFixed(1)}px`,
          `--ambient-glow-alpha:${star.glowAlpha.toFixed(2)}`,
        ].join(';'),
      }));
    });
    const now = Date.now();
    const plottedStars = stars.map((star) => {
      const started = Date.parse(String(star.started || '')) || now;
      const date = new Date(started);
      const minutes = date.getHours() * 60 + date.getMinutes();
      const jitter = _normalizedHash(star.id || star.command || star.root);
      const x = CONSTELLATION_PLOT_LEFT + (minutes / 1440) * CONSTELLATION_PLOT_WIDTH + ((jitter % 29) - 14) * 0.45;
      const elapsed = Number(star.elapsed_seconds || 0);
      const offScale = elapsed > ceilingElapsed;
      const yBase = CONSTELLATION_Y_BASELINE - ((Math.log1p(elapsed) / Math.log1p(ceilingElapsed)) * CONSTELLATION_Y_RANGE);
      const y = Math.max(18, Math.min(280, yBase + (((jitter / 31) % 31) - 15) * 0.65));
      const ageDays = Math.max(0, (now - started) / 86400000);
      const opacity = Math.max(0.28, 1 - (ageDays / 34));
      const ageGlow = 0.24 + (opacity * 0.56);
      const radius = Math.max(1.8, Math.min(7, 2 + Math.sqrt(Number(star.output_line_count || 0) + 1) * 0.18));
      const tone = _categoryTone(star.category);
      const starStyle = `--star-hue:${tone.hue};--star-saturation:${tone.saturation}%;--star-age-glow:${ageGlow.toFixed(2)}`;
      const failed = _isFailedExitCode(star.exit_code);
      return {
        star,
        started,
        x,
        y,
        radius,
        opacity,
        tone,
        starStyle,
        failed,
        offScale,
      };
    });
    const streakGroups = new Map();
    plottedStars.forEach((point) => {
      const key = String(point.star?.root || '').trim().toLowerCase();
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
        svg.appendChild(_svgEl('path', {
          class: 'status-monitor-constellation-streak',
          d: path,
          style: `--star-hue:${tone.hue};--star-saturation:${tone.saturation}%`,
        }));
      });
    });
    plottedStars.forEach(({ star, x, y, radius, opacity, starStyle, failed, offScale }, index) => {
      const starId = String(star.id || `${star.root || 'run'}:${star.started || ''}:${index}`);
      starsByNodeId.set(starId, { star, x, y });
      const node = _svgEl('g', {
        class: offScale
          ? 'status-monitor-star-node status-monitor-star-node-offscale'
          : 'status-monitor-star-node',
        tabindex: '0',
        role: 'button',
        'aria-label': `${star.root || 'run'} ${_formatStarStarted(star.started)}`,
        'data-star-id': starId,
        'data-run-id': star.id || '',
      });
      const ring = _svgEl('circle', {
        class: 'status-monitor-star-ring',
        cx: x,
        cy: y,
        r: radius + 4.5,
        style: starStyle,
      });
      const failureRing = failed ? _svgEl('circle', {
        class: 'status-monitor-star-failure-ring',
        cx: x,
        cy: y,
        r: radius + 2.2,
        opacity,
      }) : null;
      const circle = _svgEl('circle', {
        class: failed ? 'status-monitor-star status-monitor-star-failed' : 'status-monitor-star',
        cx: x,
        cy: y,
        r: radius,
        opacity,
        style: starStyle,
      });
      const hit = _svgEl('circle', {
        class: 'status-monitor-star-hit',
        cx: x,
        cy: y,
        r: Math.max(12, radius + 9),
      });
      node.append(ring);
      if (failureRing) node.appendChild(failureRing);
      if (offScale) {
        const tickTop = Math.max(4, y - radius - 7);
        const tickBottom = Math.max(tickTop + 1, y - radius - 1.5);
        node.appendChild(_svgEl('line', {
          class: 'status-monitor-star-offscale-tick',
          x1: x,
          x2: x,
          y1: tickTop,
          y2: tickBottom,
          style: starStyle,
        }));
      }
      node.append(circle, hit);
      svg.appendChild(node);
    });
    plot.append(svg, _constellationPopover());
    const sparseMessage = _constellationSparseMessage(stars.length);
    if (sparseMessage) {
      const sparse = document.createElement('div');
      sparse.className = 'status-monitor-constellation-sparse';
      sparse.textContent = sparseMessage;
      plot.appendChild(sparse);
    }
    panel.append(header, plot);
    _scheduleConstellationAspectSync(svg);
    return panel;
  }

  function _treemapWorstAspect(row, sideLength) {
    if (!row.length || sideLength <= 0) return Infinity;
    const areas = row.map(entry => entry.area).filter(area => area > 0);
    if (!areas.length) return Infinity;
    const sum = areas.reduce((total, area) => total + area, 0);
    const min = Math.min(...areas);
    const max = Math.max(...areas);
    const sideSquared = sideLength * sideLength;
    return Math.max((sideSquared * max) / (sum * sum), (sum * sum) / (sideSquared * min));
  }

  function _treemapLayoutRow(row, box, rects) {
    const rowArea = row.reduce((sum, entry) => sum + entry.area, 0);
    if (!row.length || rowArea <= 0 || box.width <= 0 || box.height <= 0) return box;
    if (box.width >= box.height) {
      const columnWidth = rowArea / box.height;
      let cursorY = box.y;
      row.forEach((entry, index) => {
        const rectHeight = index === row.length - 1
          ? (box.y + box.height) - cursorY
          : entry.area / columnWidth;
        rects.push({ item: entry.item, x: box.x, y: cursorY, width: columnWidth, height: rectHeight });
        cursorY += rectHeight;
      });
      return { x: box.x + columnWidth, y: box.y, width: Math.max(0, box.width - columnWidth), height: box.height };
    }
    const rowHeight = rowArea / box.width;
    let cursorX = box.x;
    row.forEach((entry, index) => {
      const rectWidth = index === row.length - 1
        ? (box.x + box.width) - cursorX
        : entry.area / rowHeight;
      rects.push({ item: entry.item, x: cursorX, y: box.y, width: rectWidth, height: rowHeight });
      cursorX += rectWidth;
    });
    return { x: box.x, y: box.y + rowHeight, width: box.width, height: Math.max(0, box.height - rowHeight) };
  }

  function _treemapLayout(items, x, y, width, height) {
    if (!items.length || width <= 0 || height <= 0) return [];
    const entries = items
      .map(item => ({ item, value: Math.max(1, Number(item.count || 0)) }))
      .sort((left, right) => right.value - left.value);
    const total = entries.reduce((sum, entry) => sum + entry.value, 0);
    const totalArea = width * height;
    const pending = entries.map(entry => ({
      item: entry.item,
      area: (entry.value / total) * totalArea,
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
    const popover = panel.querySelector('.status-monitor-constellation-popover');
    if (!popover || !tile) return;
    const plot = popover.parentElement;
    const succeeded = Math.max(0, Number(item?.succeeded || 0));
    const failed = Math.max(0, Number(item?.failed || 0));
    const incomplete = Math.max(0, Number(item?.incomplete || 0));
    const total = succeeded + failed + incomplete;
    const failureRate = _treemapFailureRate(item) * 100;
    const category = String(item?.category || 'Other');
    popover.querySelector('[data-field="root"]').textContent = `${item?.root || 'command'} · ${category}`;
    popover.querySelector('[data-field="command"]').textContent = `${_formatCount(item?.count || 0)} ${Number(item?.count || 0) === 1 ? 'run' : 'runs'} mapped`;
    popover.querySelector('[data-field="time"]').textContent = `${_formatCount(succeeded)} success`;
    popover.querySelector('[data-field="duration"]').textContent = `${_formatCount(failed)} fail`;
    popover.querySelector('[data-field="exit"]').textContent = `${_formatCount(incomplete)} incomplete`;
    popover.querySelector('[data-field="lines"]').textContent = total
      ? `${_formatPercent(failureRate)} fail rate`
      : 'no outcomes';

    const plotRect = plot?.getBoundingClientRect?.() || {};
    const tileRect = tile.getBoundingClientRect?.() || {};
    const plotWidth = Number(plotRect.width) || 280;
    const plotHeight = Number(plotRect.height) || 140;
    const hasPointer = event
      && Number.isFinite(Number(event.clientX))
      && Number.isFinite(Number(event.clientY));
    const targetX = hasPointer
      ? Number(event.clientX) - Number(plotRect.left || 0)
      : (Number(tileRect.left) - Number(plotRect.left || 0)) + (Number(tileRect.width) / 2);
    const targetY = hasPointer
      ? Number(event.clientY) - Number(plotRect.top || 0)
      : (Number(tileRect.top) - Number(plotRect.top || 0)) + (Number(tileRect.height) / 2);
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
    const top = _clampNumber(targetY - (popoverHeight / 2), margin, maxTop);
    popover.style.left = `${left.toFixed(1)}px`;
    popover.style.top = `${top.toFixed(1)}px`;
    popover.classList.toggle('status-monitor-constellation-popover-below', false);
    popover.classList.add('status-monitor-constellation-popover-visible');
    popover.setAttribute('aria-hidden', 'false');
  }

  function _renderTreemapPanel() {
    const insights = cachedInsights || {};
    const items = (Array.isArray(insights.command_mix) ? insights.command_mix : []).slice(0, 14);
    const panel = document.createElement('section');
    panel.className = 'status-monitor-visual-card status-monitor-treemap-card';
    const header = document.createElement('div');
    header.className = 'status-monitor-visual-header';
    const title = document.createElement('div');
    title.className = 'status-monitor-visual-title';
    title.textContent = 'Command Territory';
    const meta = document.createElement('div');
    meta.className = 'status-monitor-visual-meta';
    meta.textContent = items.length
      ? `${_formatCount(items.reduce((sum, item) => sum + Number(item.count || 0), 0))} runs · ${_insightWindowLabel('command_mix', 30)}`
      : `no commands yet · ${_insightWindowLabel('command_mix', 30)}`;
    const legend = _categoryLegend(items);
    header.append(title);
    if (legend) header.appendChild(legend);
    header.appendChild(meta);

    const map = document.createElement('div');
    map.className = 'status-monitor-treemap';
    map.addEventListener('pointerleave', () => _hideConstellationPopover(panel));
    map.addEventListener('focusout', event => {
      if (!map.contains(event.relatedTarget)) _hideConstellationPopover(panel);
    });
    if (!items.length) {
      const empty = document.createElement('div');
      empty.className = 'status-monitor-visual-empty';
      empty.textContent = 'Run history will draw command territory here.';
      map.appendChild(empty);
    } else {
      _treemapLayout(items, 0, 0, 100, 100).forEach(({ item, x, y, width, height }) => {
        const tile = document.createElement('div');
        const tone = _categoryTone(item.category);
        const highlightKey = String(item.root || item.category || '').trim().toLowerCase();
        const highlightSeed = _normalizedHash(highlightKey);
        tile.className = 'status-monitor-treemap-tile';
        const tileArea = width * height;
        const stacksDetail = height >= 30 && tileArea >= 220;
        const inlinesDetail = !stacksDetail && width >= 18 && height >= 12 && tileArea >= 120;
        if (!stacksDetail) {
          tile.classList.add('status-monitor-treemap-tile-compact');
        }
        if (inlinesDetail) {
          tile.classList.add('status-monitor-treemap-tile-inline');
        } else if (!stacksDetail) {
          tile.classList.add('status-monitor-treemap-tile-tiny');
        }
        tile.tabIndex = 0;
        tile.setAttribute('role', 'button');
        tile.style.left = `${x}%`;
        tile.style.top = `${y}%`;
        tile.style.width = `${width}%`;
        tile.style.height = `${height}%`;
        tile.style.setProperty('--category-hue', String(tone.hue));
        tile.style.setProperty('--category-saturation', `${tone.saturation}%`);
        if (tone.saturation === 0) {
          tile.style.setProperty('--category-saturation-strong', '0%');
          tile.style.setProperty('--category-saturation-mid', '0%');
          tile.style.setProperty('--category-saturation-low', '0%');
        }
        tile.style.setProperty('--tile-glow-x', `${14 + (highlightSeed % 52)}%`);
        tile.style.setProperty('--tile-glow-y', `${14 + ((_normalizedHash(`${highlightKey}:y`) % 44))}%`);
        const failureRate = _treemapFailureRate(item);
        tile.style.setProperty('--failure-alpha', failureRate ? (0.26 + (failureRate * 0.46)).toFixed(2) : '0');
        tile.style.setProperty('--failure-stop', `${Math.max(0, (failureRate * 100) - 8).toFixed(1)}%`);
        tile.style.setProperty('--failure-fade', `${Math.min(100, (failureRate * 100) + 22).toFixed(1)}%`);
        tile.setAttribute('aria-label', `${item.root}: ${item.count} run(s), ${item.category}`);
        tile.addEventListener('pointermove', event => _showTreemapPopover(panel, item, tile, event));
        tile.addEventListener('focus', () => _showTreemapPopover(panel, item, tile));
        tile.addEventListener('click', event => {
          event.preventDefault();
          event.stopPropagation();
          _clearDocumentSelection();
          _openHistoryForCommandRoot(item.root);
        });
        tile.addEventListener('keydown', event => {
          if (event.key !== 'Enter' && event.key !== ' ') return;
          event.preventDefault();
          event.stopPropagation();
          _clearDocumentSelection();
          _openHistoryForCommandRoot(item.root);
        });
        const root = document.createElement('div');
        root.className = 'status-monitor-treemap-root';
        root.textContent = item.root;
        const details = document.createElement('div');
        details.className = 'status-monitor-treemap-detail';
        const count = Number(item.count || 0);
        const completed = Number(item.succeeded || 0) + Number(item.failed || 0);
        const successRate = completed ? (Number(item.succeeded || 0) / completed) * 100 : null;
        details.textContent = count < 5
          ? `${_formatCount(item.count)} ${count === 1 ? 'run' : 'runs'}`
          : `${_formatCount(item.count)} · ${successRate === null ? 'n/a' : _formatPercent(successRate)}`;
        tile.append(root, details);
        map.appendChild(tile);
      });
    }
    const popover = _constellationPopover();
    popover.classList.add('status-monitor-treemap-popover');
    map.appendChild(popover);
    panel.append(header, map);
    return panel;
  }

  function _renderHeatmapPanel() {
    const insights = cachedInsights || {};
    const days = Array.isArray(insights.activity) ? insights.activity : [];
    const maxCount = Math.max(1, Number(insights.max_day_count || 0));
    const panel = document.createElement('section');
    panel.className = 'status-monitor-visual-card status-monitor-heatmap-card';
    const header = document.createElement('div');
    header.className = 'status-monitor-visual-header';
    const title = document.createElement('div');
    title.className = 'status-monitor-visual-title';
    title.textContent = 'Activity Heatmap';
    const meta = document.createElement('div');
    meta.className = 'status-monitor-visual-meta';
    meta.textContent = `${_formatCount(days.reduce((sum, day) => sum + Number(day.count || 0), 0))} runs / ${_insightWindowLabel('activity', Number(insights.days || days.length || 28))}`;
    const legend = document.createElement('div');
    legend.className = 'status-monitor-heatmap-legend';
    const less = document.createElement('span');
    less.textContent = 'Less';
    legend.appendChild(less);
    for (let level = 0; level <= 4; level += 1) {
      const swatch = document.createElement('span');
      swatch.className = `status-monitor-heatmap-legend-swatch status-monitor-heatmap-level-${level}`;
      swatch.setAttribute('aria-hidden', 'true');
      legend.appendChild(swatch);
    }
    const more = document.createElement('span');
    more.textContent = 'More';
    legend.appendChild(more);
    const metaGroup = document.createElement('div');
    metaGroup.className = 'status-monitor-heatmap-meta-group';
    metaGroup.append(meta, legend);
    header.append(title, metaGroup);

    const calendar = _heatmapCalendarDays(days, insights.first_run_date);
    const body = document.createElement('div');
    body.className = 'status-monitor-heatmap-body';
    if (calendar.weekCount) {
      body.style.setProperty('--status-heatmap-weeks', String(calendar.weekCount));
    }

    const months = document.createElement('div');
    months.className = 'status-monitor-heatmap-months';
    _heatmapMonthMarkers(calendar).forEach((marker) => {
      const label = document.createElement('span');
      label.className = 'status-monitor-heatmap-month';
      label.textContent = marker.label;
      label.style.gridColumn = `${marker.column}`;
      months.appendChild(label);
    });

    const weekdays = document.createElement('div');
    weekdays.className = 'status-monitor-heatmap-weekdays';
    [
      ['Mon', 1],
      ['Wed', 3],
      ['Fri', 5],
    ].forEach(([labelText, row]) => {
      const label = document.createElement('span');
      label.className = 'status-monitor-heatmap-weekday';
      label.textContent = labelText;
      label.style.gridRow = `${row}`;
      weekdays.appendChild(label);
    });

    const grid = document.createElement('div');
    grid.className = 'status-monitor-heatmap';
    const heatmapDaysByCell = new WeakMap();
    calendar.cells.forEach((day) => {
      const cell = document.createElement('span');
      const count = Number(day.count || 0);
      const level = count <= 0 ? 0 : Math.max(1, Math.min(4, Math.ceil((count / maxCount) * 4)));
      cell.className = [
        'status-monitor-heatmap-cell',
        `status-monitor-heatmap-level-${level}`,
        day.outOfRange ? 'status-monitor-heatmap-out-of-range' : '',
      ].filter(Boolean).join(' ');
      cell.dataset.date = day.date;
      cell.style.gridColumn = `${day.column}`;
      cell.style.gridRow = `${day.row}`;
      cell.tabIndex = 0;
      cell.setAttribute('aria-label', `${day.date}: ${_formatCount(count)} ${count === 1 ? 'run' : 'runs'}`);
      heatmapDaysByCell.set(cell, day);
      cell.addEventListener('focus', () => _showHeatmapPopover(panel, day, cell));
      grid.appendChild(cell);
    });
    const handleHeatmapPointer = event => {
      const target = event.target;
      const cell = target && typeof target.closest === 'function'
        ? target.closest('.status-monitor-heatmap-cell')
        : null;
      if (!cell || !body.contains(cell)) return;
      const day = heatmapDaysByCell.get(cell);
      if (day) _showHeatmapPopover(panel, day, cell, event);
    };
    body.addEventListener('pointerover', handleHeatmapPointer);
    body.addEventListener('pointermove', handleHeatmapPointer);
    body.addEventListener('pointerleave', () => _hideConstellationPopover(panel));
    body.addEventListener('focusout', event => {
      if (!body.contains(event.relatedTarget)) _hideConstellationPopover(panel);
    });
    const popover = _constellationPopover();
    popover.classList.add('status-monitor-heatmap-popover');
    body.append(months, weekdays, grid, popover);
    panel.append(header, body);
    return panel;
  }

  function _eventTickerEvents() {
    const insights = cachedInsights || {};
    const events = Array.isArray(insights.events) ? insights.events : [];
    return events.length ? events : [{ root: 'idle', command: 'waiting for run events', exit_code: null }];
  }

  function _eventTickerSignature(events) {
    return events.map(event => [
      event.root || '',
      event.command || '',
      event.started || '',
      event.finished || '',
      event.exit_code ?? 'active',
      event.elapsed_seconds ?? '',
    ].join(':')).join('|');
  }

  function _populateEventTickerRow(row, events) {
    row.replaceChildren();
    [...events, ...events].forEach(event => {
      const item = document.createElement('span');
      item.className = _isFailedExitCode(event.exit_code)
        ? 'status-monitor-event-item status-monitor-event-failed'
        : 'status-monitor-event-item';
      const code = _exitCodeLabel(event.exit_code).replace('exit ', 'exit=');
      item.textContent = `${event.root || 'run'} ${code} ${_formatDurationSeconds(event.elapsed_seconds)} · ${_truncateText(event.command || '', 44)}`;
      row.appendChild(item);
    });
  }

  function _applyEventTicker(ticker) {
    const events = _eventTickerEvents();
    const signature = _eventTickerSignature(events);
    if (ticker.dataset.eventSignature === signature) return;
    ticker.dataset.eventSignature = signature;
    const row = ticker.querySelector('.status-monitor-event-row');
    if (row) _populateEventTickerRow(row, events);
  }

  function _visualGridSignature() {
    const insights = cachedInsights || {};
    const windows = insights.windows && typeof insights.windows === 'object' ? insights.windows : {};
    const activity = Array.isArray(insights.activity) ? insights.activity : [];
    const commandMix = Array.isArray(insights.command_mix) ? insights.command_mix : [];
    const constellation = Array.isArray(insights.constellation) ? insights.constellation : [];
    const firstActivity = activity[0] || {};
    const lastActivity = activity[activity.length - 1] || {};
    const firstStar = constellation[0] || {};
    const lastStar = constellation[constellation.length - 1] || {};
    const windowSignature = ['activity', 'command_mix', 'constellation']
      .map((key) => {
        const windowInfo = windows[key] && typeof windows[key] === 'object' ? windows[key] : {};
        return [
          key,
          Number(windowInfo.days || 0),
          Number(windowInfo.total_runs || 0),
          Number(windowInfo.plotted_runs || 0),
          Number(windowInfo.available_runs || 0),
        ].join(',');
      })
      .join('|');
    const activitySignature = [
      activity.length,
      firstActivity.date || '',
      lastActivity.date || '',
      Number(lastActivity.count || 0),
      Number(lastActivity.succeeded || 0),
      Number(lastActivity.failed || 0),
      Number(lastActivity.incomplete || 0),
    ].join(':');
    const commandSignature = commandMix.map(item => [
      item.root || '',
      item.category || '',
      Number(item.count || 0),
      Number(item.succeeded || 0),
      Number(item.failed || 0),
      Number(item.incomplete || 0),
      Number(item.total_elapsed_seconds || 0).toFixed(0),
    ].join(',')).join('|');
    const constellationSignature = [
      constellation.length,
      firstStar.id || '',
      lastStar.id || '',
      lastStar.started || '',
      lastStar.finished || '',
      lastStar.exit_code ?? 'active',
      Number(lastStar.output_line_count || 0),
    ].join(':');
    return [
      insights.first_run_date || '',
      Number(insights.max_day_count || 0),
      windowSignature,
      activitySignature,
      commandSignature,
      constellationSignature,
    ].join('::');
  }

  function _renderEventTicker() {
    const events = _eventTickerEvents();
    const ticker = document.createElement('section');
    ticker.className = 'status-monitor-event-ticker';
    ticker.dataset.eventSignature = _eventTickerSignature(events);
    const label = document.createElement('div');
    label.className = 'status-monitor-event-label';
    label.textContent = 'event stream';
    const track = document.createElement('div');
    track.className = 'status-monitor-event-track';
    const row = document.createElement('div');
    row.className = 'status-monitor-event-row';
    _populateEventTickerRow(row, events);
    track.appendChild(row);
    ticker.append(label, track);
    return ticker;
  }

  function _renderVisualShowcaseGrid() {
    const grid = document.createElement('div');
    grid.className = 'status-monitor-showcase-grid';
    grid.dataset.visualSignature = _visualGridSignature();
    grid.append(_renderConstellationPanel(), _renderTreemapPanel(), _renderHeatmapPanel());
    return grid;
  }

  function _renderVisualShowcaseSection(activeRuns, options = {}) {
    const section = document.createElement('section');
    section.className = 'status-monitor-showcase';
    section.appendChild(_renderPulseStrip(activeRuns));
    section.appendChild(_renderActiveRunsSection(activeRuns, options));
    section.append(_renderVisualShowcaseGrid(), _renderEventTicker());
    return section;
  }

  function _updateVisualShowcaseSection(section, activeRuns, options = {}) {
    const pulseStrip = section.querySelector(':scope > .status-monitor-pulse-strip');
    if (pulseStrip) {
      _applyPulseStrip(pulseStrip, activeRuns);
    } else {
      section.prepend(_renderPulseStrip(activeRuns));
    }
    const runsSection = section.querySelector(':scope > .status-monitor-runs-section');
    if (runsSection) {
      _applyActiveRunsSection(runsSection, activeRuns, options);
    } else {
      const fresh = _renderActiveRunsSection(activeRuns, options);
      const pulse = section.querySelector(':scope > .status-monitor-pulse-strip');
      if (pulse) pulse.after(fresh);
      else section.appendChild(fresh);
    }
    const grid = section.querySelector(':scope > .status-monitor-showcase-grid');
    const nextSignature = _visualGridSignature();
    if (!grid) {
      const ticker = section.querySelector(':scope > .status-monitor-event-ticker');
      section.insertBefore(_renderVisualShowcaseGrid(), ticker || null);
    } else if (grid.dataset.visualSignature !== nextSignature) {
      grid.replaceWith(_renderVisualShowcaseGrid());
    }
    const ticker = section.querySelector(':scope > .status-monitor-event-ticker');
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
    const section = _statusSection('System', status.error ? 'status unavailable' : '');
    const uptime = _statusMonitorUptimeText(status);
    const latency = _isTelemetryNumber(status.latency_ms) ? Number(status.latency_ms) : null;
    section.appendChild(_statusGrid([
      _statusCard({
        label: 'Database',
        value: _statusLabel(status.db),
        tone: _statusTone(status.db),
      }),
      _statusCard({
        label: 'Redis',
        value: _statusLabel(status.redis),
        tone: _statusTone(status.redis),
      }),
      _statusCard({
        label: 'Transport',
        value: 'SSE',
        tone: 'ok',
      }),
      _statusCard({
        label: 'Uptime',
        value: uptime,
        meta: latency === null ? '' : `${latency} ms poll`,
        tone: 'idle',
        valueDataset: { statusMonitorUptimeValue: '1' },
      }),
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
    const quotaPercent = quotaBytes > 0 ? (bytesUsed / quotaBytes) * 100 : null;
    const filePercent = maxFiles > 0 ? (fileCount / maxFiles) * 100 : null;
    const section = _statusSection('Resources', workspace.error ? workspace.error : 'session workspace');
    section.appendChild(_statusGrid([
      _statusCard({
        label: 'Workspace quota',
        value: workspace.enabled === false ? 'disabled' : _formatMemoryBytes(bytesUsed),
        meta: quotaBytes > 0 ? `${_formatPercent(quotaPercent)} of ${_formatMemoryBytes(quotaBytes)}` : '',
        tone: workspace.enabled === false ? 'idle' : 'ok',
        meterPercent: quotaPercent,
      }),
      _statusCard({
        label: 'Workspace files',
        value: workspace.enabled === false ? 'disabled' : _formatCount(fileCount),
        meta: maxFiles > 0 ? `${_formatPercent(filePercent)} of ${_formatCount(maxFiles)} files` : '',
        tone: workspace.enabled === false ? 'idle' : 'ok',
        meterPercent: filePercent,
      }),
    ], 'status-monitor-grid-two'));
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
    const successRate = completed > 0 ? (succeeded / completed) * 100 : 0;
    const section = _statusSection('Session', stats.error ? 'stats unavailable' : '');
    section.appendChild(_statusGrid([
      _statusCard({
        label: 'Runs',
        value: _formatCount(total),
        meta: `${_formatCount(activeCount)} active`,
        tone: activeCount > 0 ? 'ok' : 'idle',
      }),
      _statusCard({
        label: 'Success rate',
        value: completed > 0 ? _formatPercent(successRate) : 'n/a',
        meta: `${_formatCount(succeeded)} ok / ${_formatCount(failed)} failed`,
        tone: failed > 0 ? 'warn' : 'ok',
        meterPercent: completed > 0 ? successRate : null,
      }),
      _statusCard({
        label: 'Average elapsed',
        value: _formatDurationSeconds(runs.average_elapsed_seconds),
        meta: incomplete > 0 ? `${_formatCount(incomplete)} incomplete` : '',
        tone: 'idle',
      }),
      _statusCard({
        label: 'Starred',
        value: _formatCount(stats.starred_commands || 0),
        meta: `${_formatCount(stats.snapshots || 0)} snapshots`,
        tone: 'idle',
      }),
    ]));
    return section;
  }

  function _activeRunsSummary(runs, loading) {
    if (loading) return 'Loading active runs';
    return runs.length === 1 ? '1 active run' : `${runs.length} active runs`;
  }

  function _gcResourceStateForRuns(runs) {
    const activeRunIds = new Set(
      runs.map(run => String(run?.run_id || run?.id || '')).filter(Boolean),
    );
    for (const runId of [...resourceStateByRunId.keys()]) {
      if (!activeRunIds.has(runId)) resourceStateByRunId.delete(runId);
    }
    for (const runId of [...resourceTrendByRunId.keys()]) {
      if (!activeRunIds.has(runId)) resourceTrendByRunId.delete(runId);
    }
  }

  function _populateActiveRunMeta(meta, run) {
    const tabLabel = _tabLabelForRun(run);
    const elapsed = document.createElement('span');
    elapsed.className = 'status-monitor-meta-chip status-monitor-elapsed';
    elapsed.setAttribute('data-status-monitor-started', String(run?.started || ''));
    elapsed.textContent = _formatElapsed(run?.started);
    const chips = [
      _runMetaChip(`run ${_shortRunId(run)}`),
      _runMetaChip(`pid ${run?.pid || '-'}`),
      elapsed,
    ];
    if (tabLabel) {
      chips.push(_runMetaChip(tabLabel, 'status-monitor-meta-chip-tab'));
    }
    if (run?.has_live_owner && !run?.owned_by_this_client) {
      chips.push(_runMetaChip('another browser', 'status-monitor-meta-chip-warn'));
    } else if (run?.owned_by_this_client) {
      chips.push(_runMetaChip('started here', 'status-monitor-meta-chip-ok'));
    }
    meta.replaceChildren(...chips);
    meta.dataset.metaSignature = [
      tabLabel || '',
      run?.has_live_owner ? '1' : '0',
      run?.owned_by_this_client ? '1' : '0',
    ].join('|');
  }

  function _activeRunMetaSignature(run) {
    return [
      _tabLabelForRun(run) || '',
      run?.has_live_owner ? '1' : '0',
      run?.owned_by_this_client ? '1' : '0',
    ].join('|');
  }

  function _activeRunActionsSignature(run) {
    const ptyUnavailable = _isPtyRun(run) && !_tabForRun(run);
    const hasAttach = (
      (typeof activateTab === 'function' && !!_tabForRun(run))
      || (!_isPtyRun(run) && typeof attachActiveRunFromMonitor === 'function')
    );
    const hasKill = typeof killActiveRunFromMonitor === 'function';
    return [
      hasAttach ? 'A' : '',
      ptyUnavailable ? 'P' : '',
      ptyUnavailable ? _ptyAttachUnavailableMessage(run) : '',
      hasKill ? 'K' : '',
    ].join('|');
  }

  function _openOrAttachActiveRun(run) {
    const currentTab = _tabForRun(run);
    if (currentTab && typeof activateTab === 'function') {
      activateTab(currentTab.id, { focusComposer: false });
      return Promise.resolve(true);
    }
    if (_isPtyRun(run)) {
      if (typeof showToast === 'function') showToast(_ptyAttachUnavailableMessage(run), 'error');
      return Promise.resolve(false);
    }
    if (!_isPtyRun(run) && typeof attachActiveRunFromMonitor === 'function') {
      return Promise.resolve(attachActiveRunFromMonitor(run));
    }
    return Promise.resolve(false);
  }

  function _renderActiveRunActions(run) {
    const actions = document.createElement('div');
    actions.className = 'status-monitor-actions';
    actions.dataset.actionsSignature = _activeRunActionsSignature(run);
    if ((typeof activateTab === 'function' && !!_tabForRun(run))
      || (!_isPtyRun(run) && typeof attachActiveRunFromMonitor === 'function')) {
      actions.append(_statusMonitorActionButton('Attach', 'Open or attach this run in a tab', () => {
        const latest = activeRunByRow.get(actions.closest('.status-monitor-item')) || run;
        return _openOrAttachActiveRun(latest);
      }));
    } else if (_isPtyRun(run)) {
      const unavailable = _statusMonitorActionButton('Attach', _ptyAttachUnavailableMessage(run), () => {
        const latest = activeRunByRow.get(actions.closest('.status-monitor-item')) || run;
        return _openOrAttachActiveRun(latest);
      }, {
        className: 'status-monitor-action-btn-disabled',
        closeOnSuccess: false,
      });
      unavailable.setAttribute('aria-disabled', 'true');
      actions.append(unavailable);
    }
    if (typeof killActiveRunFromMonitor === 'function') {
      actions.append(_statusMonitorActionButton('Kill', 'Kill this active run', () => {
        const latest = activeRunByRow.get(actions.closest('.status-monitor-item')) || run;
        return killActiveRunFromMonitor(latest);
      }, { className: 'status-monitor-action-btn-kill', closeOnSuccess: false }));
    }
    return actions;
  }

  function _renderActiveRunRow(run) {
    const item = document.createElement('article');
    item.className = 'status-monitor-item chrome-row row-accent-green';
    item.dataset.runId = String(run?.run_id || run?.id || '');
    activeRunByRow.set(item, run);

    const openRun = () => {
      const latest = activeRunByRow.get(item) || run;
      return _openOrAttachActiveRun(latest).then(attached => {
        if (attached) closeStatusMonitor();
        return attached;
      });
    };

    const tab = _tabForRun(run);
    if (tab || (!_isPtyRun(run) && typeof attachActiveRunFromMonitor === 'function') || _isPtyRun(run)) {
      item.classList.add('status-monitor-item-clickable', 'chrome-row-clickable');
      item.setAttribute('role', 'button');
      item.setAttribute('tabindex', '0');
      item.setAttribute('aria-label', `${tab ? 'Open tab for' : _isPtyRun(run) ? 'Show PTY attach note for' : 'Attach to'} ${String(run?.command || 'active run')}`);
      item.addEventListener('click', event => {
        if (event.target && event.target.closest && event.target.closest('.status-monitor-action-btn')) return;
        openRun().catch(err => {
          if (typeof showToast === 'function') showToast(err?.message || 'Could not open run', 'error');
        });
      });
      item.addEventListener('keydown', event => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        openRun().catch(err => {
          if (typeof showToast === 'function') showToast(err?.message || 'Could not open run', 'error');
        });
      });
    }

    const command = document.createElement('div');
    command.className = 'status-monitor-command';
    command.textContent = String(run?.command || '').trim() || '(unknown command)';

    const meta = document.createElement('div');
    meta.className = 'status-monitor-meta';
    _populateActiveRunMeta(meta, run);

    const details = document.createElement('div');
    details.className = 'status-monitor-details';
    details.append(command, meta);
    const ptyNoticeText = _ptyAttachUnavailableMessage(run);
    if (ptyNoticeText) {
      const ptyNotice = document.createElement('div');
      ptyNotice.className = 'status-monitor-pty-note';
      ptyNotice.textContent = ptyNoticeText;
      details.appendChild(ptyNotice);
    }

    const usage = _runResourceUsage(run);
    const telemetry = _runSparklinePanel(run, usage);
    const cpuValue = _formatCpuPercent(usage.cpu_percent);
    const cpuCollecting = cpuValue === 'collecting';
    const meters = document.createElement('div');
    meters.className = 'status-monitor-meters';
    meters.append(
      _statusMonitorMeter({
        label: 'CPU',
        value: cpuCollecting ? '' : cpuValue,
        percent: usage.cpu_percent,
        className: 'status-monitor-meter-cpu',
        collecting: cpuCollecting,
        ariaValue: cpuValue,
      }),
      _statusMonitorMeter({
        label: 'MEM',
        value: _formatMemoryBytes(usage.memory_bytes),
        percent: _memoryPercent(usage.memory_bytes),
        className: 'status-monitor-meter-mem',
      }),
    );

    const meterRail = document.createElement('div');
    meterRail.className = 'status-monitor-meter-rail';
    meterRail.appendChild(meters);
    const actions = _renderActiveRunActions(run);
    if (actions.childElementCount) meterRail.append(actions);
    item.append(details, telemetry, meterRail);
    return item;
  }

  function _updateActiveRunRow(row, run) {
    activeRunByRow.set(row, run);

    const meta = row.querySelector(':scope > .status-monitor-details > .status-monitor-meta');
    if (meta && meta.dataset.metaSignature !== _activeRunMetaSignature(run)) {
      _populateActiveRunMeta(meta, run);
    } else if (meta) {
      // Signature unchanged but the elapsed chip's data attribute should still
      // track the run's started time in case the API ever rewrites it; the
      // 1s tick timer rewrites textContent.
      const elapsed = meta.querySelector('.status-monitor-elapsed');
      if (elapsed) {
        const started = String(run?.started || '');
        if (elapsed.getAttribute('data-status-monitor-started') !== started) {
          elapsed.setAttribute('data-status-monitor-started', started);
          elapsed.textContent = _formatElapsed(run?.started);
        }
      }
    }

    const details = row.querySelector(':scope > .status-monitor-details');
    if (details) {
      const expectedNotice = _ptyAttachUnavailableMessage(run);
      let notice = details.querySelector(':scope > .status-monitor-pty-note');
      if (expectedNotice) {
        if (!notice) {
          notice = document.createElement('div');
          notice.className = 'status-monitor-pty-note';
          details.appendChild(notice);
        }
        if (notice.textContent !== expectedNotice) notice.textContent = expectedNotice;
      } else if (notice) {
        notice.remove();
      }
    }

    const usage = _runResourceUsage(run);
    const samples = _recordResourceTrend(run, usage);
    const cpuPath = row.querySelector('.status-monitor-sparkline-cpu');
    const memPath = row.querySelector('.status-monitor-sparkline-mem');
    if (cpuPath) cpuPath.setAttribute('d', _trendPath(samples, 'cpu'));
    if (memPath) memPath.setAttribute('d', _trendPath(samples, 'mem'));

    const cpuValue = _formatCpuPercent(usage.cpu_percent);
    const cpuCollecting = cpuValue === 'collecting';
    const cpuMeter = row.querySelector('.status-monitor-meter-cpu');
    if (cpuMeter) {
      _updateStatusMonitorMeter(cpuMeter, {
        label: 'CPU',
        value: cpuCollecting ? '' : cpuValue,
        percent: usage.cpu_percent,
        collecting: cpuCollecting,
        ariaValue: cpuValue,
      });
    }
    const memMeter = row.querySelector('.status-monitor-meter-mem');
    if (memMeter) {
      _updateStatusMonitorMeter(memMeter, {
        label: 'MEM',
        value: _formatMemoryBytes(usage.memory_bytes),
        percent: _memoryPercent(usage.memory_bytes),
      });
    }

    const meterRail = row.querySelector(':scope > .status-monitor-meter-rail');
    if (meterRail) {
      const expectedSig = _activeRunActionsSignature(run);
      const existingActions = meterRail.querySelector(':scope > .status-monitor-actions');
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
    const section = _statusSection('Runs', _activeRunsSummary(runs, loading));
    section.classList.add('status-monitor-runs-section');
    const runList = document.createElement('div');
    runList.className = 'status-monitor-runs-list';
    section.appendChild(runList);
    _applyActiveRunsSection(section, runs, options);
    return section;
  }

  function _applyActiveRunsSection(section, runs, options = {}) {
    const loading = !!options.loadingActiveRuns;
    const summary = _activeRunsSummary(runs, loading);
    const header = section.querySelector(':scope > .status-monitor-section-header');
    if (header) {
      let metaEl = header.querySelector(':scope > .status-monitor-section-meta');
      if (summary) {
        if (!metaEl) {
          metaEl = document.createElement('div');
          metaEl.className = 'status-monitor-section-meta';
          header.appendChild(metaEl);
        }
        if (metaEl.textContent !== summary) metaEl.textContent = summary;
      } else if (metaEl) {
        metaEl.remove();
      }
    }
    section.dataset.activeRunCount = String(runs.length);

    const runList = section.querySelector(':scope > .status-monitor-runs-list');
    if (!runList) return;
    runList.classList.toggle('status-monitor-runs-list-many', runs.length >= 5);
    runList.classList.toggle('status-monitor-runs-list-medium', runs.length >= 3 && runs.length < 5);

    if (loading) {
      const existingEmpty = runList.querySelector(':scope > .status-monitor-empty');
      if (existingEmpty && existingEmpty.textContent === 'Loading active runs...'
          && runList.children.length === 1) {
        return;
      }
      const empty = document.createElement('div');
      empty.className = 'status-monitor-empty status-monitor-runs-empty';
      empty.textContent = 'Loading active runs...';
      runList.replaceChildren(empty);
      return;
    }

    _gcResourceStateForRuns(runs);

    const emptyNode = runList.querySelector(':scope > .status-monitor-empty');
    if (emptyNode) emptyNode.remove();

    if (!runs.length) {
      runList.querySelectorAll(':scope > .status-monitor-item').forEach(node => node.remove());
      const empty = document.createElement('div');
      empty.className = 'status-monitor-empty status-monitor-runs-empty';
      empty.textContent = 'No active runs.';
      runList.appendChild(empty);
      return;
    }

    const existingRows = new Map();
    runList.querySelectorAll(':scope > .status-monitor-item').forEach(node => {
      const id = node.dataset.runId || '';
      if (id) existingRows.set(id, node);
    });

    const seen = new Set();
    let cursor = null;
    for (const run of runs) {
      const id = String(run?.run_id || run?.id || '');
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
    const showcase = listEl.querySelector(':scope > .status-monitor-showcase')
      || _renderVisualShowcaseSection(activeRuns, options);
    if (showcase.parentElement === listEl) _updateVisualShowcaseSection(showcase, activeRuns, options);
    const fallbackSummary = activeRuns.length === 1 ? '1 active run' : `${activeRuns.length} active runs`;
    if (summaryEl.dataset) {
      if (!options.loadingActiveRuns && latestPulseData?.summaryPrefix) {
        summaryEl.dataset.statusMonitorSummaryPrefix = latestPulseData.summaryPrefix;
      } else {
        delete summaryEl.dataset.statusMonitorSummaryPrefix;
      }
    }
    summaryEl.textContent = options.loadingActiveRuns ? 'Loading active runs...' : (latestPulseData?.meta || fallbackSummary);
    _replaceDashboardChildren([
      showcase,
      _renderServicesSection(),
      _renderWorkspaceSection(),
      _renderSessionStatsSection(activeRuns.length),
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
      // Insights are loaded once on open and refreshed on the >0 → 0
      // transition only. A freshly completed run lands in the heatmap
      // "today" cell, the treemap percentages, and the constellation
      // without continuous polling.
      if (!forceInsights && previousRunCount > 0 && runs.length === 0) {
        await _refreshHistoryInsights();
        _renderDashboard(runs);
      }
      _scheduleOpenCpuFollowup(runs);
    } catch (err) {
      if (summaryEl) summaryEl.textContent = 'Unavailable';
      if (listEl) {
        listEl.replaceChildren();
        const error = document.createElement('div');
        error.className = 'status-monitor-empty status-monitor-error';
        error.textContent = err?.message || 'Status monitor failed to load.';
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
      if (isOpen && document.visibilityState === 'visible') void refreshStatusMonitor();
    }, CPU_SAMPLE_WARMUP_MS);
  }

  function _startClosedPolling() {
    if (closedPollTimer) return;
    closedPollTimer = setInterval(() => {
      if (isOpen || document.visibilityState !== 'visible') return;
      void _refreshActiveRunCache({ render: false }).catch(() => {});
    }, CLOSED_POLL_MS);
  }

  function _stopClosedPolling() {
    if (closedPollTimer) clearInterval(closedPollTimer);
    closedPollTimer = null;
  }

  function _primeStatusMonitorSamples() {
    _clearWarmupTimer();
    if (document.visibilityState !== 'visible') {
      _startClosedPolling();
      return;
    }
    void _refreshActiveRunCache({ render: isOpen }).then((runs) => {
      if (!runs.length) return;
      _startClosedPolling();
      warmupTimer = setTimeout(() => {
        warmupTimer = null;
        if (document.visibilityState === 'visible') {
          void _refreshActiveRunCache({ render: isOpen }).catch(() => {});
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
      if (isOpen && document.visibilityState === 'visible') void refreshStatusMonitor();
    }, POLL_MS);
    if (tickTimer) clearInterval(tickTimer);
    tickTimer = setInterval(() => {
      if (isOpen && document.visibilityState === 'visible') {
        _updateElapsedTimers();
        _updateLiveUptimeDisplays();
      }
    }, 1000);
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
    const source = String(options.source || 'command');
    _ensureMonitor();
    isOpen = true;
    _positionMonitor();
    const mobile = _isMobileStatusMonitor();
    document.body.classList.toggle('status-monitor-mobile-open', mobile);
    document.body.classList.toggle('status-monitor-desktop-open', !mobile);
    monitorEl?.classList.toggle('chrome-drawer', !mobile);
    monitorEl?.classList.toggle('status-monitor-modal', !mobile);
    scrimEl?.classList.remove('u-hidden');
    monitorEl?.classList.remove('u-hidden');
    if (monitorEl) monitorEl.dataset.source = source;
    if (typeof pauseBackgroundRunStreamsForStatusMonitor === 'function') {
      pauseBackgroundRunStreamsForStatusMonitor();
    }
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
      if (typeof showToast === 'function') showToast(err?.message || 'Status monitor failed to load', 'error');
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
    if (typeof resumeBackgroundRunStreamsAfterStatusMonitor === 'function') {
      resumeBackgroundRunStreamsAfterStatusMonitor();
    }
    document.body.classList.remove('status-monitor-mobile-open');
    document.body.classList.remove('status-monitor-desktop-open');
    scrimEl?.classList.add('u-hidden');
    monitorEl?.classList.add('u-hidden');
  }

  function isStatusMonitorOpen() {
    return isOpen;
  }

  function _makeHudCellOpenMonitor(cell, source, label) {
    if (!cell || cell.dataset.statusMonitorTrigger === '1') return;
    cell.dataset.statusMonitorTrigger = '1';
    cell.classList.add('hud-cell-clickable', 'hud-action-cell');
    cell.setAttribute('role', 'button');
    cell.setAttribute('tabindex', '0');
    cell.setAttribute('aria-haspopup', 'dialog');
    cell.setAttribute('aria-label', label);
    cell.addEventListener('click', () => { void openStatusMonitor({ source }); });
    cell.addEventListener('keydown', event => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      void openStatusMonitor({ source });
    });
  }

  function _clearStatusAffordance() {
    const cell = document.getElementById('hud-status-cell');
    if (!cell) return;
    cell.classList.remove('hud-status-expandable', 'hud-status-affordance-pulse');
    cell.querySelector('.status-monitor-status-glyph')?.remove();
    cell.title = '';
  }

  function _activeHudStatusIsRunning() {
    return String(document.getElementById('status')?.textContent || '').trim().toUpperCase() === 'RUNNING';
  }

  function _bindHudTriggers() {
    _makeHudCellOpenMonitor(
      document.getElementById('hud-status-cell'),
      'status',
      'Open status monitor from status',
    );
    _makeHudCellOpenMonitor(
      document.getElementById('hud-last-exit-cell') || document.getElementById('hud-last-exit')?.closest('.hud-cell'),
      'last-exit',
      'Open status monitor from last exit',
    );
    _makeHudCellOpenMonitor(
      document.getElementById('hud-tabs-cell') || document.getElementById('hud-tabs')?.closest('.hud-cell'),
      'tabs',
      'Open status monitor from tabs',
    );
  }

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && isOpen) closeStatusMonitor();
  });
  document.addEventListener('visibilitychange', () => {
    if (isOpen && document.visibilityState === 'visible') {
      _startPulseAnimation();
      void refreshStatusMonitor();
    } else if (isOpen) {
      _stopPulseAnimation();
    } else if (document.visibilityState === 'visible' && cachedRuns.length) {
      _primeStatusMonitorSamples();
    }
  });
  document.addEventListener('app:status-changed', event => {
    const status = String(event?.detail?.status || '').trim().toLowerCase();
    _clearStatusAffordance();
    if (status === 'running') {
      _primeStatusMonitorSamples();
    } else if (!isOpen) {
      _clearWarmupTimer();
      _stopClosedPolling();
    }
  });
  window.addEventListener('resize', () => {
    if (!isOpen) return;
    _positionMonitor();
    document.querySelectorAll('.status-monitor-constellation').forEach(_scheduleConstellationAspectSync);
  });

  _bindHudTriggers();
  _clearStatusAffordance();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _bindHudTriggers, { once: true });
  }

  window.openStatusMonitor = openStatusMonitor;
  window.closeStatusMonitor = closeStatusMonitor;
  window.isStatusMonitorOpen = isStatusMonitorOpen;
  window.refreshStatusMonitor = refreshStatusMonitor;
}());
