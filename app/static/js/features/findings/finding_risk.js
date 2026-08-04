// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Compact, explainable labels for stored public CVE risk signals.

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

function findingRiskSummary(finding) {
  const risk = findingPrimaryRisk(finding);
  if (!risk) return '';
  const labels = [];
  if (risk.kev?.listed) labels.push('CISA KEV');
  const probability = finiteNumber(risk.epss?.probability);
  if (probability !== null) labels.push(`EPSS ${(probability * 100).toFixed(1)}%`);
  const cvss = finiteNumber(risk.cvss?.score);
  if (cvss !== null) labels.push(`CVSS ${cvss.toFixed(1)}`);
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
  return labels.join(' · ');
}

export { findingPrimaryRisk, findingRiskSummary };
