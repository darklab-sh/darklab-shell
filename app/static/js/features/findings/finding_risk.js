// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Compact, explainable labels for stored public CVE risk signals.

const NO_STORED_CVE_RISK_LABEL = 'No stored KEV, EPSS, or NVD data';

function findingPrimaryRisk(finding) {
  if (finding?.risk && typeof finding.risk === 'object') return finding.risk;
  if (Array.isArray(finding?.cve_risk) && finding.cve_risk[0]) return finding.cve_risk[0];
  return null;
}

function finiteNumber(value) {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function feedAgeLabel(value) {
  const hours = finiteNumber(value);
  if (hours === null) return '';
  if (hours < 48) return `${Math.max(0, Math.round(hours))}h old`;
  return `${Math.max(1, Math.round(hours / 24))}d old`;
}

function publicFeedLabels(risk) {
  const labels = [];
  const feeds = [
    ['CISA KEV', risk.kev],
    ['EPSS', risk.epss],
  ];
  let refreshDisabled = false;
  feeds.forEach(([name, feed]) => {
    const origin = String(feed?.origin || '').toLowerCase();
    if (!['bundled', 'live', 'local'].includes(origin)) return;
    const age = feedAgeLabel(feed?.age_hours);
    labels.push(`${name} ${origin}${age ? ` (${age})` : ''}`);
    if (feed?.live_refresh_enabled === false) refreshDisabled = true;
  });
  if (refreshDisabled) {
    labels.push('live refresh off; set cve_risk.refresh_enabled: true');
  }
  return labels;
}

function findingRiskSummary(finding) {
  const risk = findingPrimaryRisk(finding);
  if (!risk) return '';
  const labels = [];
  if (risk.kev?.listed) labels.push('CISA KEV');
  const probability = finiteNumber(risk.epss?.probability);
  if (probability !== null) labels.push(`EPSS ${(probability * 100).toFixed(1)}%`);
  const percentile = finiteNumber(risk.epss?.percentile);
  if (percentile !== null) labels.push(`EPSS ${(percentile * 100).toFixed(1)}th percentile`);
  const cvss = finiteNumber(risk.cvss?.score);
  if (cvss !== null) labels.push(`CVSS ${cvss.toFixed(1)}`);
  if (risk.public_exploit_available === true) labels.push('Public exploit reference available');
  const advisoryStatus = String(risk.advisory_status || '').toLowerCase();
  if (['disputed', 'rejected', 'withdrawn'].includes(advisoryStatus)) {
    labels.push(`NVD ${advisoryStatus}`);
  }
  const freshness = [risk.kev?.freshness, risk.epss?.freshness, risk.cvss?.freshness]
    .map(value => String(value || ''));
  if (freshness.includes('failed')) labels.push('source refresh failed');
  else if (freshness.includes('stale')) labels.push('stale source data');
  else if (cvss === null && String(risk.cvss?.freshness || '') === 'unavailable') {
    labels.push('NVD unavailable');
  }
  labels.push(...publicFeedLabels(risk));
  return labels.join(' · ');
}

export { NO_STORED_CVE_RISK_LABEL, findingPrimaryRisk, findingRiskSummary };
