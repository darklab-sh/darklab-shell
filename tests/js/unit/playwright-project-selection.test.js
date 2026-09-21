// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, it } from 'vitest'
import { selectedProjectNames, selectedWebServers } from '../../../.tooling/playwright.project-selection.js'

describe('isolated browser server selection', () => {
  it('uses collected tests, including nested and repeated profile projects', () => {
    const report = { suites: [{ specs: [{ tests: [{ projectName: 'open' }, { projectName: 'mixed' }] }],
      suites: [{ specs: [{ tests: [{ projectName: 'mixed' }] }] }] }] }
    expect(selectedProjectNames(report)).toEqual(['mixed', 'open'])
    expect(selectedProjectNames({ suites: [] })).toEqual([])
  })

  it('preserves the selected server ports, ordering and isolation settings', () => {
    const servers = [
      ['open', { url: 'http://localhost:5001', reuseExistingServer: false }],
      ['mixed', { url: 'https://localhost:5007', reuseExistingServer: false }],
    ]
    expect(selectedWebServers(servers, '["mixed"]')).toEqual([servers[1][1]])
    expect(selectedWebServers(servers, '["mixed","open"]')).toEqual(servers.map(([, server]) => server))
    expect(selectedWebServers(servers, '')).toEqual(servers.map(([, server]) => server))
    expect(selectedWebServers(servers, '[]')).toEqual([])
    expect(() => selectedWebServers(servers, '["typo"]')).toThrow('Unknown Playwright project')
    expect(() => selectedWebServers(servers, 'private-invalid-input')).toThrow('Invalid Playwright project selection')
  })
})
