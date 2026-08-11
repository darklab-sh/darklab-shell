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
    expect(findingRiskSummary({
      risk: {
        kev: {
          listed: true,
          freshness: 'stale',
          origin: 'bundled',
          age_hours: 72,
          live_refresh_enabled: false,
        },
        epss: {
          probability: 0.1836,
          freshness: 'stale',
          origin: 'bundled',
          age_hours: 48,
          live_refresh_enabled: false,
        },
      },
    })).toBe(
      'CISA KEV · EPSS 18.4% · stale source data · CISA KEV bundled (3d old) · '
      + 'EPSS bundled (2d old) · live refresh off; set cve_risk.refresh_enabled: true',
    );
  });

  it('shows stored CVSS and non-active NVD states without inventing a risk score', () => {
    expect(findingRiskSummary({
      risk: {
        kev: { listed: false, freshness: 'current' },
        epss: { freshness: 'current' },
        advisory_status: 'disputed',
        cvss: { score: 8.8, freshness: 'current' },
      },
    })).toBe('CVSS 8.8 · NVD disputed');
    expect(findingRiskSummary({
      risk: {
        kev: { listed: false, freshness: 'current' },
        epss: { probability: null, freshness: 'current' },
        cvss: { score: null, freshness: 'unavailable' },
      },
    })).toBe('NVD unavailable');
  });
});
