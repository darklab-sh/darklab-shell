// Status Monitor endpoint loading and dashboard data aggregation.

window.DarklabStatusMonitorData = (() => {
  function _safeObject(data) {
    return data && typeof data === 'object' ? data : {};
  }

  function create({ apiFetch }) {
    if (typeof apiFetch !== 'function') {
      throw new Error('DarklabStatusMonitorData requires apiFetch');
    }

    async function loadActiveRuns() {
      const resp = await apiFetch('/history/active');
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.error || `HTTP ${resp.status}`);
      return Array.isArray(data?.runs) ? data.runs : [];
    }

    async function loadSystemStatus() {
      const startedAt = Date.now();
      const resp = await apiFetch('/status');
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.error || `HTTP ${resp.status}`);
      const payload = _safeObject(data);
      payload.latency_ms = Date.now() - startedAt;
      payload.uptime_received_at_ms = Date.now();
      return payload;
    }

    async function loadWorkspaceStatus() {
      const resp = await apiFetch('/workspace/files');
      const data = await resp.json();
      if (!resp.ok) return { enabled: false, error: data?.error || `HTTP ${resp.status}` };
      return _safeObject(data);
    }

    async function loadSessionStats() {
      const resp = await apiFetch('/history/stats');
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.error || `HTTP ${resp.status}`);
      return _safeObject(data);
    }

    async function loadHistoryInsights() {
      const resp = await apiFetch('/history/insights');
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.error || `HTTP ${resp.status}`);
      return _safeObject(data);
    }

    async function refreshHistoryInsights() {
      try {
        return await loadHistoryInsights();
      } catch (err) {
        return { error: err?.message || 'Unavailable' };
      }
    }

    async function refreshDashboardData({ cachedInsights = null, includeInsights = false } = {}) {
      const shouldLoadInsights = includeInsights || !cachedInsights;
      const [status, workspace, stats, insights] = await Promise.allSettled([
        loadSystemStatus(),
        loadWorkspaceStatus(),
        loadSessionStats(),
        shouldLoadInsights ? loadHistoryInsights() : Promise.resolve(cachedInsights),
      ]);
      return {
        status: status.status === 'fulfilled'
          ? status.value
          : { error: status.reason?.message || 'Unavailable' },
        workspace: workspace.status === 'fulfilled'
          ? workspace.value
          : { enabled: false, error: workspace.reason?.message || 'Unavailable' },
        stats: stats.status === 'fulfilled'
          ? stats.value
          : { error: stats.reason?.message || 'Unavailable' },
        insights: shouldLoadInsights
          ? (
            insights.status === 'fulfilled'
              ? insights.value
              : { error: insights.reason?.message || 'Unavailable' }
          )
          : cachedInsights,
        loadedInsights: shouldLoadInsights,
      };
    }

    return {
      loadActiveRuns,
      loadSystemStatus,
      loadWorkspaceStatus,
      loadSessionStats,
      loadHistoryInsights,
      refreshHistoryInsights,
      refreshDashboardData,
    };
  }

  return { create };
})();
