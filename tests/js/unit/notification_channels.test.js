// @vitest-environment jsdom

import { readFileSync } from 'fs'
import { resolve } from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const NOTIFICATION_CHANNELS_SRC = readFileSync(
  resolve(process.cwd(), 'app/static/js/features/preferences/notification_channels.js'),
  'utf8',
)

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: vi.fn(async () => body),
  }
}

function loadNotificationChannels({ apiFetch = vi.fn(), showConfirm = vi.fn() } = {}) {
  document.body.innerHTML = `
    <div data-options-panel="notifications" hidden></div>
    <button id="options-notification-refresh-btn"></button>
    <button id="options-notification-new-btn"></button>
    <div id="options-notification-msg"></div>
    <div id="options-notification-list"></div>
  `
  window.apiFetch = apiFetch
  window.showConfirm = showConfirm
  new Function(NOTIFICATION_CHANNELS_SRC)()
  return {
    list: document.getElementById('options-notification-list'),
    msg: document.getElementById('options-notification-msg'),
    refreshNotificationChannels: window.refreshNotificationChannels,
    openNotificationChannelEditor: window.openNotificationChannelEditor,
  }
}

describe('notification channel preferences panel', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    delete window.apiFetch
    delete window.showConfirm
    delete window.refreshNotificationChannels
    delete window.openNotificationChannelEditor
    document.body.innerHTML = ''
  })

  it('renders token-required and empty states from refresh responses', async () => {
    const apiFetch = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ error: 'session_token_required' }, 401))
      .mockResolvedValueOnce(jsonResponse({ channels: [] }))
    const { list, msg, refreshNotificationChannels } = loadNotificationChannels({ apiFetch })

    await refreshNotificationChannels({ force: true })
    expect(msg.textContent).toContain('Generate or set a session token')
    expect(msg.classList.contains('is-error')).toBe(true)
    expect(list.textContent).toContain('No notification channels yet.')

    await refreshNotificationChannels({ force: true })
    expect(msg.textContent).toBe('')
    expect(list.textContent).toContain('Add a channel to get pinged when long runs finish.')
  })

  it('validates required secrets and submits editor payloads without exposing them in the list', async () => {
    const apiFetch = vi.fn(async (url, options = {}) => {
      if (url === '/session/notification-channels' && options.method === 'POST') {
        return jsonResponse({ channel: { id: 'ntc_webhook' } }, 201)
      }
      return jsonResponse({ channels: [] })
    })
    const showConfirm = vi.fn(async (options) => {
      const saveAction = options.actions.find(action => action.id === 'save')
      const firstResult = await saveAction.onActivate()
      expect(firstResult).toBe(false)
      expect(options.content.querySelector('.form-error').textContent).toBe('Webhook URL is required.')

      options.content.querySelector('input[placeholder="Label"]').value = 'Ops hook'
      options.content.querySelector('[data-secret-field="url"]').value = 'https://example.invalid/hook'
      options.content.querySelector('[data-config-field="timeout_seconds"]').value = '7'
      return saveAction.onActivate()
    })
    const { openNotificationChannelEditor, msg } = loadNotificationChannels({ apiFetch, showConfirm })

    await openNotificationChannelEditor()

    const postCall = apiFetch.mock.calls.find(([url, options]) => (
      url === '/session/notification-channels' && options?.method === 'POST'
    ))
    expect(postCall).toBeTruthy()
    const body = JSON.parse(postCall[1].body)
    expect(body).toEqual({
      kind: 'webhook',
      label: 'Ops hook',
      config: { timeout_seconds: '7' },
      triggers: ['run_complete'],
      secret_values: { url: 'https://example.invalid/hook' },
      muted: false,
    })
    expect(msg.textContent).toBe('Notification channel added.')
  })

  it('renders channel actions and routes test, mute, and delete requests', async () => {
    let channels = [{
      id: 'ntc_chat',
      kind: 'telegram',
      label: 'Ops chat',
      config: { chat_id: '12345' },
      triggers: ['run_complete', 'watcher_error'],
      muted: false,
      secret_fields: [{ name: 'bot_token', configured: true }],
    }]
    const apiFetch = vi.fn(async (url, options = {}) => {
      if (url === '/session/notification-channels') return jsonResponse({ channels })
      if (url === '/session/notification-channels/ntc_chat/test') {
        return jsonResponse({ queued: 1, events: [{ event_id: 'nte_test', status: 'sent', last_error: '' }] })
      }
      if (url === '/session/notification-channels/ntc_chat' && options.method === 'PATCH') {
        channels = [{ ...channels[0], muted: JSON.parse(options.body).muted }]
        return jsonResponse({ channel: channels[0] })
      }
      if (url === '/session/notification-channels/ntc_chat' && options.method === 'DELETE') {
        channels = []
        return jsonResponse({ removed: true })
      }
      throw new Error(`unexpected request ${url}`)
    })
    const showConfirm = vi.fn(async () => 'delete')
    const { list, msg, refreshNotificationChannels } = loadNotificationChannels({ apiFetch, showConfirm })

    await refreshNotificationChannels({ force: true })
    expect(list.textContent).toContain('Ops chat')
    expect(list.textContent).toContain('run complete, watcher error · chat 12345')

    const buttons = Array.from(list.querySelectorAll('button'))
    buttons.find(button => button.textContent === 'Test').click()
    await vi.waitFor(() => expect(msg.textContent).toBe('Test notification delivered.'))

    buttons.find(button => button.textContent === 'Mute').click()
    await vi.waitFor(() => expect(msg.textContent).toBe('Notification channel muted.'))
    expect(JSON.parse(apiFetch.mock.calls.find(([url, options]) => (
      url === '/session/notification-channels/ntc_chat' && options?.method === 'PATCH'
    ))[1].body).muted).toBe(true)

    Array.from(list.querySelectorAll('button')).find(button => button.textContent === 'Delete').click()
    await vi.waitFor(() => expect(msg.textContent).toBe('Notification channel deleted.'))
    expect(showConfirm).toHaveBeenCalledWith(expect.objectContaining({ tone: 'danger' }))
    expect(list.textContent).toContain('No notification channels yet.')
  })
})
