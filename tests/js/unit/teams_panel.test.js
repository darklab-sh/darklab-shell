import { beforeEach, describe, expect, it, vi } from 'vitest'
import { loadAppFns } from './helpers/app_harness.js'

const ROLE_CAPABILITIES = {
  owner: [
    'view_team',
    'manage_owners',
    'manage_members',
    'manage_invites',
    'manage_recovery',
    'archive_team',
    'run_commands',
    'manage_history',
    'manage_automation',
    'mutate_projects',
    'triage_findings',
    'manage_workflows',
    'manage_notifications',
    'manage_secrets',
  ],
  admin: [
    'view_team',
    'manage_members',
    'manage_invites',
    'run_commands',
    'manage_history',
    'manage_automation',
    'mutate_projects',
    'triage_findings',
    'manage_workflows',
    'manage_notifications',
    'manage_secrets',
  ],
  operator: [
    'view_team',
    'run_commands',
    'manage_history',
    'manage_automation',
    'mutate_projects',
    'triage_findings',
  ],
  viewer: ['view_team'],
}

function apiResponse(payload = {}, { ok = true, status = 200, statusText = 'OK' } = {}) {
  return {
    ok,
    status,
    statusText,
    json: vi.fn(async () => payload),
  }
}

function teamList(role) {
  return [{
    id: 'team_permissions_1',
    name: 'Permissions Team',
    slug: 'permissions-team',
    status: 'active',
    member: {
      id: 'tmem_actor',
      role,
      capabilities: ROLE_CAPABILITIES[role],
      display_name: 'Current user',
    },
  }]
}

function teamDetail(role, overrides = {}) {
  return {
    team: {
      id: 'team_permissions_1',
      name: 'Permissions Team',
      slug: 'permissions-team',
      status: 'active',
      member: {
        id: 'tmem_actor',
        role,
        capabilities: ROLE_CAPABILITIES[role],
        display_name: 'Current user',
      },
      ...(overrides.team || {}),
    },
    members: overrides.members || [
      {
        id: 'tmem_actor',
        role,
        capabilities: ROLE_CAPABILITIES[role],
        display_name: 'Current user',
        status: 'active',
        is_current: true,
      },
      {
        id: 'tmem_owner',
        role: 'owner',
        display_name: 'Team owner',
        status: 'active',
      },
      {
        id: 'tmem_operator',
        role: 'operator',
        display_name: 'Operator',
        status: 'active',
      },
    ],
    invites: overrides.invites || [{
      id: 'tinv_active',
      role: 'operator',
      label: 'Active invite',
      use_count: 0,
      max_uses: 1,
      status: 'active',
    }],
    recovery_codes: overrides.recovery_codes || [{
      id: 'trec_active',
      created_at: '2026-05-28T00:00:00Z',
    }],
  }
}

function buildApiFetch({ role = 'owner', detail = null, inviteFailure = null, recoveryFailure = null } = {}) {
  return vi.fn(async (url, opts = {}) => {
    if (url === '/session/preferences') return apiResponse({ preferences: {} })
    if (url === '/session/secrets') return apiResponse({ secrets: [] })
    if (url === '/session/teams') return apiResponse({ teams: teamList(role) })
    if (url === '/session/teams/team_permissions_1') return apiResponse(detail || teamDetail(role))
    if (url === '/session/teams/team_permissions_1/invites' && opts.method === 'POST') {
      if (inviteFailure) return apiResponse(inviteFailure, { ok: false, status: 403, statusText: 'Forbidden' })
      return apiResponse({ invite: { code: 'tinv_once' } })
    }
    if (url === '/session/teams/team_permissions_1/recovery/rotate' && opts.method === 'POST') {
      if (recoveryFailure) return apiResponse(recoveryFailure, { ok: false, status: 403, statusText: 'Forbidden' })
      return apiResponse({ recovery_code: 'trec_once' })
    }
    if (url === '/log') return apiResponse({ ok: true })
    return apiResponse({})
  })
}

async function loadTeamsPanel({
  role = 'owner',
  apiFetch = buildApiFetch({ role }),
  showConfirm = vi.fn(async () => 'confirm'),
  showToast = vi.fn(),
} = {}) {
  const harness = await loadAppFns({
    apiFetch,
    showConfirm,
    showToast,
    sessionId: `tok_team_panel_${role}`,
  })
  harness.activateOptionsTab('teams')
  await vi.waitFor(() => {
    expect(document.getElementById('options-teams-list').textContent).toContain('Permissions Team')
  })
  document.querySelector('[data-team-action="select-team"]').click()
  await vi.waitFor(() => {
    expect(document.getElementById('options-team-detail').textContent).toContain('Members')
  })
  return { ...harness, apiFetch, showConfirm, showToast }
}

function memberForm(memberId) {
  return document.querySelector(`.options-team-member-form[data-member-id="${memberId}"]`)
}

describe('Options Teams permissions UI', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    document.body.replaceChildren()
  })

  it.each([
    ['owner', {
      inviteForm: true,
      archiveAction: true,
      rotateDisabled: false,
      ownerRoleDisabled: false,
      operatorRoleDisabled: false,
      operatorRemove: true,
    }],
    ['admin', {
      inviteForm: true,
      archiveAction: false,
      rotateDisabled: true,
      ownerRoleDisabled: true,
      operatorRoleDisabled: false,
      operatorRemove: true,
    }],
    ['operator', {
      inviteForm: false,
      archiveAction: false,
      rotateDisabled: true,
      ownerRoleDisabled: true,
      operatorRoleDisabled: true,
      operatorRemove: false,
    }],
    ['viewer', {
      inviteForm: false,
      archiveAction: false,
      rotateDisabled: true,
      ownerRoleDisabled: true,
      operatorRoleDisabled: true,
      operatorRemove: false,
    }],
  ])('renders capability-gated controls for %s', async (role, expected) => {
    await loadTeamsPanel({ role })

    expect(document.querySelector('[data-team-invite-form]') !== null).toBe(expected.inviteForm)
    expect(document.querySelector('[data-team-action="archive-team"]') !== null).toBe(expected.archiveAction)
    expect(document.querySelector('[data-team-action="rotate-recovery"]').disabled).toBe(expected.rotateDisabled)
    expect(memberForm('tmem_owner').querySelector('[name="role"]').disabled).toBe(expected.ownerRoleDisabled)
    expect(memberForm('tmem_operator').querySelector('[name="role"]').disabled).toBe(expected.operatorRoleDisabled)
    expect(memberForm('tmem_operator').querySelector('[data-team-action="remove-member"]') !== null)
      .toBe(expected.operatorRemove)
    expect(memberForm('tmem_actor').querySelector('[name="display_name"]').disabled).toBe(false)
  })

  it('allows the current owner role to change only when another active owner exists', async () => {
    const singleOwnerDetail = teamDetail('owner', {
      members: [
        {
          id: 'tmem_actor',
          role: 'owner',
          capabilities: ROLE_CAPABILITIES.owner,
          display_name: 'Current user',
          status: 'active',
          is_current: true,
        },
        {
          id: 'tmem_operator',
          role: 'operator',
          display_name: 'Operator',
          status: 'active',
        },
      ],
    })
    await loadTeamsPanel({
      role: 'owner',
      apiFetch: buildApiFetch({ role: 'owner', detail: singleOwnerDetail }),
    })

    const singleOwnerRole = memberForm('tmem_actor').querySelector('[name="role"]')
    expect(singleOwnerRole.disabled).toBe(true)
    expect(singleOwnerRole.title).toBe('Promote another owner before changing your role.')

    document.body.replaceChildren()
    const twoOwnerDetail = teamDetail('owner')
    await loadTeamsPanel({
      role: 'owner',
      apiFetch: buildApiFetch({ role: 'owner', detail: twoOwnerDetail }),
    })

    expect(memberForm('tmem_actor').querySelector('[name="role"]').disabled).toBe(false)
  })

  it('shows invite statuses and only offers revoke for active invites', async () => {
    const detail = teamDetail('owner', {
      invites: [
        { id: 'tinv_active', role: 'operator', label: 'Active invite', use_count: 0, max_uses: 1 },
        { id: 'tinv_used', role: 'viewer', label: 'Used invite', use_count: 1, max_uses: 1 },
        {
          id: 'tinv_expired',
          role: 'operator',
          label: 'Expired invite',
          use_count: 0,
          max_uses: 1,
          expires_at: '2020-01-01T00:00:00Z',
        },
        {
          id: 'tinv_revoked',
          role: 'operator',
          label: 'Revoked invite',
          use_count: 0,
          max_uses: 1,
          revoked_at: '2026-05-28T00:00:00Z',
        },
      ],
    })

    await loadTeamsPanel({ role: 'owner', apiFetch: buildApiFetch({ role: 'owner', detail }) })

    const inviteText = Array.from(document.querySelectorAll('.options-team-invite-row'))
      .map(row => row.textContent)
      .join(' ')
    expect(inviteText).toContain('Active invite')
    expect(inviteText).toContain('Active')
    expect(inviteText).toContain('Used invite')
    expect(inviteText).toContain('Used')
    expect(inviteText).toContain('Expired invite')
    expect(inviteText).toContain('Expired')
    expect(inviteText).toContain('Revoked invite')
    expect(inviteText).toContain('Revoked')
    expect(document.querySelectorAll('[data-team-action="revoke-invite"]')).toHaveLength(1)
  })

  it('copies a newly created invite code even after the detail pane refreshes', async () => {
    const { copyTextToClipboard, showToast } = await loadTeamsPanel({ role: 'owner' })

    document.querySelector('[data-team-invite-form]').dispatchEvent(new Event('submit', {
      bubbles: true,
      cancelable: true,
    }))

    await vi.waitFor(() => {
      expect(document.getElementById('options-team-detail').textContent).toContain('Copy this now')
    })
    const copyButton = document.querySelector('[data-team-action="copy-code"]')
    copyButton.dataset.codeValue = ''
    copyButton.click()

    await vi.waitFor(() => {
      expect(copyTextToClipboard).toHaveBeenCalledWith('tinv_once')
    })
    expect(showToast).toHaveBeenCalledWith('Code copied', 'success')
  })

  it('lets the Teams tab switch back to Personal scope', async () => {
    const { showToast } = await loadTeamsPanel({ role: 'owner' })

    document.querySelector('#options-teams-list [data-team-action="switch-team"]').click()
    await vi.waitFor(() => {
      expect(window.getActiveTeamId()).toBe('team_permissions_1')
    })

    const personalRow = Array.from(document.querySelectorAll('#options-teams-list .options-team-row'))
      .find(row => row.textContent.includes('Personal'))
    expect(personalRow).toBeTruthy()
    expect(personalRow.textContent).toContain('Private scope')
    personalRow.querySelector('[data-team-action="switch-personal"]').click()

    expect(window.getActiveTeamId()).toBe('')
    expect(document.getElementById('team-scope-label').textContent).toBe('Personal')
    expect(showToast).toHaveBeenCalledWith('Personal scope selected', 'success')
  })

  it('surfaces failed invite creation with inline status and safe client logging', async () => {
    const apiFetch = buildApiFetch({
      role: 'owner',
      inviteFailure: { message: 'invite denied' },
    })
    const { logClientError } = await loadTeamsPanel({ role: 'owner', apiFetch })

    document.querySelector('[data-team-invite-form]').dispatchEvent(new Event('submit', {
      bubbles: true,
      cancelable: true,
    }))

    await vi.waitFor(() => {
      expect(document.getElementById('options-teams-msg').textContent).toBe('invite denied')
    })
    expect(document.getElementById('options-teams-msg').classList.contains('is-error')).toBe(true)
    const failureLog = logClientError.mock.calls.find(([context, error]) => (
      String(context).startsWith('TEAM_ACTION_FAILED')
      && String(context).includes('"action":"create_invite"')
      && String(context).includes('"team_id":"team_permissions_1"')
      && error.message === 'invite denied'
    ))
    expect(failureLog).toBeTruthy()
  })

  it('surfaces failed recovery rotation with confirmation and safe client logging', async () => {
    const apiFetch = buildApiFetch({
      role: 'owner',
      recoveryFailure: { message: 'recovery denied' },
    })
    const showConfirm = vi.fn(async () => 'confirm')
    const { logClientError } = await loadTeamsPanel({ role: 'owner', apiFetch, showConfirm })

    document.querySelector('[data-team-action="rotate-recovery"]').click()

    await vi.waitFor(() => {
      expect(document.getElementById('options-teams-msg').textContent).toBe('recovery denied')
    })
    expect(showConfirm).toHaveBeenCalledWith(expect.objectContaining({
      actions: expect.arrayContaining([
        expect.objectContaining({ id: 'confirm', label: 'Rotate' }),
      ]),
    }))
    const failureLog = logClientError.mock.calls.find(([context, error]) => (
      String(context).startsWith('TEAM_ACTION_FAILED')
      && String(context).includes('"action":"rotate_recovery_code"')
      && String(context).includes('"team_id":"team_permissions_1"')
      && error.message === 'recovery denied'
    ))
    expect(failureLog).toBeTruthy()
  })
})
