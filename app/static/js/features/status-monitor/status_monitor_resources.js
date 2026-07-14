// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

function createStatusMonitorResources({ core, svgEl, pathFromPoints }) {
  const resourceStateByRunId = new Map();
  const resourceTrendByRunId = new Map();
  const isTelemetryNumber = core.isTelemetryNumber;

  function runResourceUsage(run) {
    const runId = String(run?.run_id || run?.id || '');
    const usage = run?.resource_usage && typeof run.resource_usage === 'object'
      ? run.resource_usage
      : {};
    const previous = runId ? resourceStateByRunId.get(runId) : null;
    const now = Date.now();
    const cpuSeconds = isTelemetryNumber(usage.cpu_seconds)
      ? Number(usage.cpu_seconds)
      : null;
    let cpuPercent = previous?.cpu_percent;
    if (cpuSeconds !== null && previous && isTelemetryNumber(previous.cpu_seconds)) {
      const elapsedSeconds = Math.max(0, (now - Number(previous.sampled_at || now)) / 1000);
      const deltaCpu = cpuSeconds - Number(previous.cpu_seconds);
      if (elapsedSeconds >= 0.25 && deltaCpu >= 0) {
        cpuPercent = (deltaCpu / elapsedSeconds) * 100;
      }
    }
    if (cpuSeconds !== null && !isTelemetryNumber(cpuPercent)) {
      cpuPercent = Number.NaN;
    }
    const memoryBytes = isTelemetryNumber(usage.memory_bytes)
      ? Number(usage.memory_bytes)
      : previous?.memory_bytes;
    const resolved = {
      cpu_percent: cpuPercent,
      cpu_seconds: cpuSeconds ?? previous?.cpu_seconds,
      memory_bytes: memoryBytes,
      sampled_at: cpuSeconds !== null ? now : previous?.sampled_at,
    };
    if (runId && (
      isTelemetryNumber(resolved.cpu_percent)
      || isTelemetryNumber(resolved.cpu_seconds)
      || isTelemetryNumber(resolved.memory_bytes)
    )) {
      resourceStateByRunId.set(runId, resolved);
    }
    return resolved;
  }

  function recordResourceTrend(run, usage) {
    const runId = String(run?.run_id || run?.id || '');
    if (!runId) return [];
    const samples = resourceTrendByRunId.get(runId) || [];
    const now = Date.now();
    const previous = samples[samples.length - 1];
    if (!previous || now - previous.t >= 750) {
      samples.push({
        t: now,
        cpu: isTelemetryNumber(usage.cpu_percent) ? Number(usage.cpu_percent) : null,
        mem: isTelemetryNumber(usage.memory_bytes) ? Number(usage.memory_bytes) : null,
      });
      while (samples.length > 60) samples.shift();
      resourceTrendByRunId.set(runId, samples);
    }
    return samples;
  }

  function trendPath(samples, key, width = 160, height = 34) {
    const values = samples.map(sample => sample[key]).filter(value => isTelemetryNumber(value));
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
      const value = isTelemetryNumber(sample[key]) ? Number(sample[key]) : min;
      const x = samples.length <= 1 ? width : (index / (samples.length - 1)) * width;
      const y = height - (((value - min) / spread) * (height - 6)) - 3;
      return [x, y];
    });
    return pathFromPoints(points);
  }

  function runSparklinePanel(run, usage) {
    const samples = recordResourceTrend(run, usage);
    const panel = document.createElement('div');
    panel.className = 'status-monitor-spark-panel';

    const header = document.createElement('div');
    header.className = 'status-monitor-spark-header';
    const title = document.createElement('span');
    title.className = 'status-monitor-spark-title';
    title.textContent = 'CPU/MEM 60s';
    header.append(title);

    const svg = svgEl('svg', {
      class: 'status-monitor-sparkline',
      viewBox: '0 0 160 34',
      role: 'img',
      'aria-label': 'CPU and memory trend',
      preserveAspectRatio: 'none',
    });
    svg.append(
      svgEl('path', {
        class: 'status-monitor-sparkline-grid',
        d: 'M0 17 L160 17 M40 0 L40 34 M80 0 L80 34 M120 0 L120 34',
      }),
      svgEl('path', { class: 'status-monitor-sparkline-cpu', d: trendPath(samples, 'cpu') }),
      svgEl('path', { class: 'status-monitor-sparkline-mem', d: trendPath(samples, 'mem') }),
    );

    panel.append(header, svg);
    return panel;
  }

  function runsNeedCpuFollowup(runs) {
    return (Array.isArray(runs) ? runs : []).some((run) => {
      const runId = String(run?.run_id || run?.id || '');
      if (!runId) return false;
      const state = resourceStateByRunId.get(runId);
      return state && isTelemetryNumber(state.cpu_seconds) && !isTelemetryNumber(state.cpu_percent);
    });
  }

  function gcForRuns(runs) {
    const activeRunIds = new Set(
      (Array.isArray(runs) ? runs : []).map(run => String(run?.run_id || run?.id || '')).filter(Boolean),
    );
    for (const runId of [...resourceStateByRunId.keys()]) {
      if (!activeRunIds.has(runId)) resourceStateByRunId.delete(runId);
    }
    for (const runId of [...resourceTrendByRunId.keys()]) {
      if (!activeRunIds.has(runId)) resourceTrendByRunId.delete(runId);
    }
  }

  return {
    clear: () => {
      resourceStateByRunId.clear();
      resourceTrendByRunId.clear();
    },
    getState: runId => resourceStateByRunId.get(String(runId || '')),
    runResourceUsage,
    recordResourceTrend,
    trendPath,
    runSparklinePanel,
    runsNeedCpuFollowup,
    gcForRuns,
  };
}

const DarklabStatusMonitorResources = { create: createStatusMonitorResources };

export {
  DarklabStatusMonitorResources,
  createStatusMonitorResources,
};
