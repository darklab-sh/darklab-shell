import { test, expect } from '@playwright/test'
import { browserSessionId, ensurePromptReady, seedProjectOverviewFixture } from './helpers.js'

const PROJECT_ID = 'project-overview'
const TARGET_ID = 'ent_overview_1'
const TARGET_VALUE = 'api.darklab.test'

async function installProjectOverviewFixture(page) {
  await page.addInitScript(({ projectId, targetId, targetValue }) => {
    const originalFetch = window.fetch.bind(window)
    const requests = []
    window.__projectOverviewRequests = requests

    const project = {
      id: projectId,
      name: 'Overview Project',
      slug: 'overview-project',
      status: 'active',
      counts: {
        runs: 1,
        entities: 1,
        findings: 1,
        artifacts: 0,
        targets: 1,
        packages: 0,
      },
      finding_summary: {
        review_states: { new: 1 },
        severities: { high: 1 },
      },
    }

    const summary = {
      project,
      counts: project.counts,
      finding_summary: project.finding_summary,
      links: [],
      targets: [{
        id: targetId,
        type: 'domain',
        value: targetValue,
        review_state: 'confirmed',
        source: 'manual',
      }],
      entities: [{
        id: targetId,
        type: 'domain',
        value: targetValue,
        source: 'target',
        metadata: {},
      }],
      runs: [{
        id: 'run_overview_1',
        command: `nuclei -u https://${targetValue}`,
        started: '2026-06-25T10:00:00+00:00',
        finished: '2026-06-25T10:00:02+00:00',
        exit_code: 0,
      }],
      findings: [{
        id: 'finding_overview_1',
        title: 'TLS certificate expires soon',
        raw_line: 'certificate expires within 30 days',
        severity: 'high',
        review_state: 'new',
        run_id: 'run_overview_1',
        run_command: `nuclei -u https://${targetValue}`,
        target_id: targetId,
        target_value: targetValue,
        line_number: 4,
      }],
      artifacts: [],
      packages: [],
      partial: false,
    }

    const overview = {
      payload_version: 1,
      project: { id: projectId, name: 'Overview Project' },
      rollups: {
        target_count: 1,
        open_port_count: 2,
        service_count: 2,
        provider_count: 1,
        recent_change_state: 'windowed',
        certificate_statuses: {
          expired: 0,
          expiring_14d: 0,
          expiring_30d: 1,
          healthy: 0,
          unknown: 0,
        },
        finding_severities: {
          critical: 0,
          high: 1,
          medium: 0,
          low: 0,
          info: 0,
        },
      },
      recent_changes: [{
        fire_id: 'fire_overview_1',
        state: 'changed',
        target_ids: [targetId],
      }],
      targets: [{
        id: targetId,
        entity_id: targetId,
        type: 'domain',
        value: targetValue,
        display_label: `domain:${targetValue}`,
        target_review_state: 'confirmed',
        source_flags: {
          has_intel: true,
          has_findings: true,
          has_recent_changes: true,
        },
        open_ports: [80, 443],
        services: ['http', 'https'],
        certificate: {
          status: 'expiring_30d',
          expires_at: '2026-07-15T00:00:00+00:00',
          days_until_expiry: 20,
          last_checked_at: '2026-06-25T00:00:00+00:00',
        },
        top_finding_severity: 'high',
        finding_counts: {
          by_review_state: { new: 1 },
          suppressed: 0,
        },
        intel_summary: {
          providers_with_data: ['censys'],
          highlights: [{ label: 'Censys saw https on 443' }],
        },
        recent_change_markers: [{ fire_id: 'fire_overview_1' }],
        deep_link_hints: {
          entities: { target_id: targetId },
          findings: { target_id: targetId, orphan_filter: 'all', severity: 'high' },
        },
      }],
    }

    const json = (payload, status = 200) => new Response(JSON.stringify(payload), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })

    window.fetch = async (input, init = {}) => {
      const rawUrl = typeof input === 'string' ? input : input?.url
      const url = new URL(rawUrl, window.location.origin)
      const path = `${url.pathname}${url.search}`
      requests.push({ method: String(init?.method || 'GET'), path })

      if (url.pathname === '/projects') {
        return json({ projects: [project], total: 1, limit: 50, offset: 0 })
      }
      if (url.pathname === '/projects/active') {
        return json({ project })
      }
      if (url.pathname === `/projects/${projectId}/summary`) {
        return json(summary)
      }
      if (url.pathname === `/projects/${projectId}/overview`) {
        return json(overview)
      }
      if (url.pathname === `/projects/${projectId}/targets`) {
        return json({ targets: summary.targets, total: 1, limit: 50, offset: 0, has_more: false })
      }
      if (url.pathname === `/projects/${projectId}/entities`) {
        return json({ entities: summary.entities, total: 1, limit: 50, offset: 0, has_more: false })
      }
      if (url.pathname === `/projects/${projectId}/findings`) {
        return json({
          findings: summary.findings,
          total: 1,
          limit: 50,
          offset: 0,
          has_more: false,
          group_counts: { [summary.findings[0].run_command]: 1 },
          collapsed_group_counts: {},
          group_order: [summary.findings[0].run_command],
        })
      }

      return originalFetch(input, init)
    }
  }, { projectId: PROJECT_ID, targetId: TARGET_ID, targetValue: TARGET_VALUE })
}

async function openDesktopProjects(page) {
  await page.goto('/')
  await ensurePromptReady(page)
  await page.locator('.rail-nav [data-action="projects"]').click()
  await expect(page.locator('#project-workspace-overlay')).toHaveClass(/\bopen\b/)
  await expect(page.locator('#project-workspace-body')).not.toContainText('Loading projects...')
}

async function openMobileProjects(page) {
  await page.goto('/')
  await ensurePromptReady(page)
  await page.locator('#hamburger-btn').click()
  await page.locator('#mobile-menu-sheet [data-menu-action="projects"]').click()
  await expect(page.locator('#project-workspace-overlay')).toHaveClass(/\bopen\b/)
  await expect(page.locator('#project-mobile-root')).toBeVisible()
  await expect(page.locator('#project-mobile-body')).not.toContainText('Loading projects...')
}

async function createRealOverviewProject(page, testInfo) {
  const projectName = `Real Overview ${Date.now()}`
  const targetValue = `overview-${Date.now()}.example.com`
  await page.goto('/')
  await ensurePromptReady(page)
  const sessionId = await browserSessionId(page)
  const created = await page.evaluate(async ({ name, value }) => {
    const projectResp = await apiFetch('/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    if (!projectResp.ok) throw new Error(`project create failed: ${projectResp.status}`)
    const project = (await projectResp.json()).project
    const activeResp = await apiFetch('/projects/active', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: project.id }),
    })
    if (!activeResp.ok) throw new Error(`active project failed: ${activeResp.status}`)
    const targetResp = await apiFetch(`/projects/${encodeURIComponent(project.id)}/targets`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'domain', value }),
    })
    if (!targetResp.ok) throw new Error(`target create failed: ${targetResp.status}`)
    const target = (await targetResp.json()).target
    return { project, target }
  }, { name: projectName, value: targetValue })
  seedProjectOverviewFixture(testInfo, {
    sessionId,
    projectId: created.project.id,
    targetId: created.target.id,
    targetValue,
  })
  return { projectId: created.project.id, targetId: created.target.id, targetValue }
}

test.describe('project overview browser contract', () => {
  test('renders a populated desktop Overview and deep-links to filtered Findings', async ({ page }) => {
    await installProjectOverviewFixture(page)
    await openDesktopProjects(page)

    const overviewTab = page.locator('[data-project-tab="overview"]')
    await overviewTab.click()
    await expect(overviewTab).toHaveClass(/\bis-active\b/)

    const overview = page.locator('.project-overview-root')
    await expect(overview.locator('.project-overview-target-title')).toHaveText(TARGET_VALUE)
    await expect(overview.locator('.project-overview-target-detail')).toContainText('80, 443')
    await expect(overview.locator('.project-overview-target-chips')).toContainText('Finding: High')
    await expect(overview.locator('.project-overview-target-chips')).toContainText('Cert: <=30d')
    await expect(overview.locator('.project-overview-target-chips')).not.toContainText('Intel: None')
    await expect(overview.locator('.project-overview-highlights')).toContainText('Censys saw https on 443')

    await overview.locator('[data-project-overview-action="findings"]').click()
    await expect(page.locator('[data-project-tab="findings"]')).toHaveClass(/\bis-active\b/)
    await expect(page.locator('.project-explorer-item-title')).toContainText('TLS certificate expires soon')

    await expect.poll(() => page.evaluate(({ targetId }) => {
      const requests = Array.isArray(window.__projectOverviewRequests) ? window.__projectOverviewRequests : []
      return requests.some(({ path }) => (
        path.includes(`/projects/${encodeURIComponent('project-overview')}/findings`)
        && path.includes(`target_id=${encodeURIComponent(targetId)}`)
        && path.includes('severity=high')
      ))
    }, { targetId: TARGET_ID })).toBe(true)
  })

  test('uses the real Overview endpoint and filters Findings by backend target id', async ({ page }, testInfo) => {
    test.setTimeout(60_000)
    const fixture = await createRealOverviewProject(page, testInfo)
    const overviewResponse = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return response.request().method() === 'GET'
        && url.pathname === `/projects/${fixture.projectId}/overview`
    })
    await page.locator('.rail-nav [data-action="projects"]').click()
    await expect(page.locator('#project-workspace-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#project-workspace-body')).not.toContainText('Loading projects...')

    const overviewTab = page.locator('[data-project-tab="overview"]')
    await overviewTab.click()
    expect((await overviewResponse).ok()).toBe(true)

    const overview = page.locator('.project-overview-root')
    await expect(overview.locator('.project-overview-target-title')).toHaveText(fixture.targetValue)
    await expect(overview.locator('.project-overview-target-detail')).toContainText('443')
    await expect(overview.locator('.project-overview-target-chips')).toContainText('Finding: High')
    await expect(overview.locator('.project-overview-target-chips')).toContainText('Cert: <=30d')

    const findingsResponse = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return response.request().method() === 'GET'
        && url.pathname === `/projects/${fixture.projectId}/findings`
        && url.searchParams.get('target_id') === fixture.targetId
        && url.searchParams.get('severity') === 'high'
    })
    await overview.locator('[data-project-overview-action="findings"]').click()
    expect((await findingsResponse).ok()).toBe(true)
    await expect(page.locator('[data-project-tab="findings"]')).toHaveClass(/\bis-active\b/)
    await expect(page.locator('.project-explorer-item-title')).toContainText('Real Overview filtered finding')
    await expect(page.locator('#project-explorer-body')).not.toContainText('No findings')
  })
})

test.describe('project overview mobile browser contract', () => {
  test.use({ hasTouch: true, isMobile: true })

  test('renders the Overview tab inside the mobile project detail sheet', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await installProjectOverviewFixture(page)
    await openMobileProjects(page)

    const projectRow = page.locator(`.project-mobile-row[data-project-id="${PROJECT_ID}"]`)
    await projectRow.locator('[data-project-mobile-action="open-project"]').click()
    await expect(page.locator('#project-mobile-detail-view')).toBeVisible()
    await page.locator('[data-project-mobile-detail-tab="overview"]').click()
    await expect(page.locator('[data-project-mobile-detail-tab="overview"]')).toHaveClass(/\bis-active\b/)

    const overview = page.locator('#project-mobile-detail-body .project-overview-root.is-mobile')
    await expect(overview.locator('.project-overview-target-title')).toHaveText(TARGET_VALUE)
    await expect(overview.locator('.project-overview-target-chips')).toContainText('Finding: High')
    await expect(overview.locator('.project-overview-target-chips')).toContainText('Cert: <=30d')
    await expect(overview.locator('[data-project-overview-action="entities"]')).toBeVisible()
    await expect(overview.locator('[data-project-overview-action="findings"]')).toBeVisible()
  })
})
