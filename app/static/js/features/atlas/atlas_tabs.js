// Session Entity Atlas tab metadata and formatting helpers.

(function initAtlasTabs(global) {
  const tabs = [
    { id: 'findings', label: 'Findings', type: '', countKey: 'findings' },
    { id: 'ip', label: 'Hosts/IPs', type: 'ip', countKey: 'ip' },
    { id: 'domain', label: 'Domains', type: 'domain', countKey: 'domain' },
    { id: 'hash', label: 'Hashes', type: 'hash', countKey: 'hash' },
    { id: 'cve', label: 'CVEs', type: 'cve', countKey: 'cve' },
    { id: 'url', label: 'URLs', type: 'url', countKey: 'url' },
  ];

  function tabById(id) {
    return tabs.find(tab => tab.id === id) || tabs[0];
  }

  function labelForType(type) {
    const found = tabs.find(tab => tab.type === type);
    return found ? found.label : String(type || 'Entity');
  }

  function countForTab(tab, summary) {
    if (!tab || !summary) return 0;
    if (tab.id === 'findings') return Number(summary.findings || 0);
    const counts = summary.counts && typeof summary.counts === 'object' ? summary.counts : {};
    return Number(counts[tab.countKey] || 0);
  }

  function totalEntityCount(summary) {
    if (!summary || !summary.counts || typeof summary.counts !== 'object') return Number(summary?.total || 0);
    return Object.values(summary.counts).reduce((total, value) => total + Number(value || 0), 0);
  }

  global.DarklabAtlasTabs = {
    tabs,
    tabById,
    labelForType,
    countForTab,
    totalEntityCount,
  };
})(typeof window !== 'undefined' ? window : globalThis);
