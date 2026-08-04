// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Compact, explainable labels for stored public CVE risk signals.

function findingPrimaryRisk(finding) {
  if (finding?.risk && typeof finding.risk === 'object') return finding.risk;
  if (Array.isArray(finding?.cve_risk) && finding.cve_risk[0]) return finding.cve_risk[0];
  return null;
}

function findingRiskSummary(finding) {
  const risk = findingPrimaryRisk(finding);
  if (!risk) return '';
  const labels = [];
  if (risk.kev?.listed) labels.push('CISA KEV');
  const probability = Number(risk.epss?.probability);
  if (Number.isFinite(probability)) labels.push(`EPSS ${(probability * 100).toFixed(1)}%`);
  const freshness = [risk.kev?.freshness, risk.epss?.freshness].map(value => String(value || ''));
  if (freshness.includes('stale')) labels.push('stale source data');
  return labels.join(' · ');
}

export { findingPrimaryRisk, findingRiskSummary };
