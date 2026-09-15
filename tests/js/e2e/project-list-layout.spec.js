// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { test, expect } from '@playwright/test'
import { ensurePromptReady } from './helpers.js'

async function seedProjects(page, names) {
  await page.evaluate(async (projectNames) => {
    for (const name of projectNames) {
      const response = await apiFetch('/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })
      if (!response.ok) throw new Error(`Project setup failed: ${response.status}`)
    }
  }, names)
}

async function expectContainedCards(rows) {
  await expect.poll(() => rows.evaluateAll((cards) => cards.flatMap((card) => {
    const bounds = card.getBoundingClientRect()
    const style = getComputedStyle(card)
    const bottom = bounds.bottom - parseFloat(style.paddingBottom) - parseFloat(style.borderBottomWidth)
    const overflowing = Array.from(card.children).some((content) => {
      const contentBounds = content.getBoundingClientRect()
      return contentBounds.bottom > bottom + 1
        || contentBounds.left < bounds.left - 1
        || contentBounds.right > bounds.right + 1
    })
    return overflowing
      ? [card.textContent.trim()]
      : []
  })), { message: 'Project names and badges must stay inside their cards' }).toEqual([])
}

test('project sidebar cards stay readable as projects are added and deleted', async ({ page }, testInfo) => {
  test.setTimeout(60_000)
  await page.setViewportSize({ width: 1280, height: 1000 })
  await page.goto('/')
  await ensurePromptReady(page)
  await seedProjects(page, Array.from({ length: 6 }, (_, index) => `Layout project ${index + 1}`))
  await page.locator('.rail-nav [data-action="projects"]').click()

  const list = page.locator('#project-workspace-body')
  const rows = list.locator('.project-workspace-row')
  const form = page.locator('#project-workspace-create-form')
  await expect(rows).toHaveCount(6)
  await expectContainedCards(rows)
  const first = rows.first()
  const firstId = await first.getAttribute('data-project-id')
  const initialHeight = (await first.boundingBox()).height
  // Exercise the wrapped badge layout from the reported screenshots.
  expect(await first.locator('.project-workspace-count').evaluateAll((chips) =>
    new Set(chips.map((chip) => Math.round(chip.getBoundingClientRect().top))).size,
  )).toBeGreaterThan(1)

  for (const count of [7, 8]) {
    await form.locator('input').fill(`Layout project ${count}`)
    await form.getByRole('button', { name: 'Create', exact: true }).click()
    await expect(rows).toHaveCount(count)
    await expect(rows.filter({ hasText: `Layout project ${count}` })).toHaveClass(/is-active/)
    await expectContainedCards(rows)
    expect((await list.locator(`[data-project-id="${firstId}"]`).boundingBox()).height)
      .toBeCloseTo(initialHeight, 0)
  }

  for (const count of [8, 7]) {
    await rows.filter({ hasText: `Layout project ${count}` }).click()
    await page.locator('#project-explorer-body [data-project-action="delete"]').click()
    await page.locator('#confirm-host [data-confirm-action-id="delete"]').click()
    await expect(rows).toHaveCount(count - 1)
    await expectContainedCards(rows)
  }

  await seedProjects(page, [
    'A project with a long name that wraps across several lines in the sidebar',
    ...Array.from({ length: 7 }, (_, index) => `Extra project ${index + 1}`),
  ])
  await page.locator('.project-workspace-close').click()
  await page.locator('.rail-nav [data-action="projects"]').click()
  await expect(rows).toHaveCount(14)

  for (const viewport of [{ width: 1280, height: 1000 }, { width: 1000, height: 620 }]) {
    await page.setViewportSize(viewport)
    await expectContainedCards(rows)
    expect(await list.evaluate((element) => element.scrollHeight - element.clientHeight)).toBeGreaterThan(0)
    await rows.last().scrollIntoViewIfNeeded()
    await expect(rows.last()).toBeInViewport()
    await expect(form).toBeInViewport()
    await rows.last().click()
    await expect(rows.last()).toHaveAttribute('aria-current', 'true')
    await expect(page.locator('#project-explorer-body')).toContainText('Layout project 6')
    await expect(page.locator('#project-workspace-modal')).toBeInViewport({ ratio: 1 })
  }
  await page.screenshot({ path: testInfo.outputPath('projects-sidebar-overflow.png') })
})

test.describe('mobile project list', () => {
  test.use({ hasTouch: true, isMobile: true })

  test('cards remain contained and the last project is reachable', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 700 })
    await page.goto('/')
    await ensurePromptReady(page)
    await seedProjects(page, Array.from({ length: 8 }, (_, index) => `Mobile layout project ${index + 1}`))
    await page.locator('#hamburger-btn').click()
    await page.locator('#mobile-menu-sheet [data-menu-action="projects"]').click()
    const list = page.locator('#project-mobile-body')
    const rows = list.locator('.project-mobile-row')
    await expect(rows).toHaveCount(8)
    await expectContainedCards(rows)
    expect(await list.evaluate((element) => element.scrollHeight - element.clientHeight)).toBeGreaterThan(0)
    await rows.last().scrollIntoViewIfNeeded()
    await expect(rows.last()).toBeInViewport()
    await expect(page.locator('#project-mobile-new-btn')).toBeInViewport()
    await rows.last().locator('[data-project-mobile-action="open-project"]').click()
    await expect(page.locator('#project-mobile-detail-view')).toBeVisible()
    await expect(page.locator('#project-mobile-detail-topbar')).toContainText('Mobile layout project 8')
  })
})
