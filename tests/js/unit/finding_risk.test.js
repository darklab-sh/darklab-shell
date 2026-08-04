// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, it } from 'vitest';

import {
  findingPrimaryRisk,
  findingRiskSummary,
} from '../../../app/static/js/features/findings/finding_risk.js';

describe('finding public CVE risk labels', () => {
  it('keeps compact labels explainable and explicit about stale data', () => {
    const risk = {
      kev: { listed: true, freshness: 'current' },
      epss: { probability: 0.1836, freshness: 'stale' },
    };
    const finding = { cve_risk: [risk] };

    expect(findingPrimaryRisk(finding)).toBe(risk);
    expect(findingRiskSummary(finding)).toBe('CISA KEV · EPSS 18.4% · stale source data');
    expect(findingRiskSummary({ risk: { kev: { listed: false }, epss: {} } })).toBe('');
  });
});
