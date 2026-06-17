// @vitest-environment jsdom

import { readFileSync } from 'fs'
import { resolve } from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { stripEsmExports } from './helpers/extract.js'

const NOTIFICATION_CHANNELS_SRC = stripEsmExports(readFileSync(
  resolve(process.cwd(), 'app/static/js/features/preferences/notification_channels.js'),
  'utf8',
))

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: vi.fn(async () => body),
  }
}

const CHANNEL_KIND_CONTRACT = {
  kinds: [
    {
      kind: 'webhook',
      label: 'Webhook',
      secret_fields: [{ name: 'url', label: 'Webhook URL' }],
      config_fields: [{ name: 'timeout_seconds', label: 'Timeout seconds', optional: true }],
    },
    {
      kind: 'telegram',
      label: 'Telegram',
      secret_fields: [{ name: 'bot_token', label: 'Bot token' }],
      config_fields: [
        { name: 'chat_id', label: 'Chat ID' },
        { name: 'timeout_seconds', label: 'Timeout seconds', optional: true },
      ],
    },
  ],
  triggers: [
    { value: 'run_complete', label: 'Run complete' },
    { value: 'watcher_error', label: 'Watcher error' },
  ],
}

function loadNotificationChannels({ apiFetch = vi.fn(), showConfirm = vi.fn(), showToast = vi.fn() } = {}) {
  document.body.innerHTML = `
    <div data-options-panel="notifications" hidden></div>
    <button id="options-notification-refresh-btn"></button>
    <button id="options-notification-new-btn"></button>
    <div id="options-notification-msg"></div>
    <div id="options-notification-list"></div>
  `
  window.apiFetch = apiFetch
  window.showConfirm = showConfirm
  window.showToast = showToast
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
    delete window.showToast
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

  it('uses cached channel metadata for tab revisits and preserves it after forced load failures', async () => {
    const apiFetch = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({
        channels: [{
          id: 'ntc_cached',
          kind: 'slack',
          label: 'Ops cached',
          config: {},
          triggers: ['run_complete'],
          muted: false,
          secret_fields: [{ name: 'url', configured: true }],
        }],
      }))
      .mockResolvedValueOnce(jsonResponse({
        error: 'rate_limit_exceeded',
        message: 'Rate limit exceeded. Please slow down.',
      }, 429))
    const { list, msg, refreshNotificationChannels } = loadNotificationChannels({ apiFetch })

    await refreshNotificationChannels()
    expect(list.textContent).toContain('Ops cached')
    expect(apiFetch).toHaveBeenCalledTimes(1)

    await refreshNotificationChannels()
    expect(apiFetch).toHaveBeenCalledTimes(1)
    expect(msg.textContent).toBe('')

    await refreshNotificationChannels({ force: true })
    expect(apiFetch).toHaveBeenCalledTimes(2)
    expect(list.textContent).toContain('Ops cached')
    expect(msg.textContent).toContain('Rate limit exceeded. Please slow down.')
    expect(msg.classList.contains('is-error')).toBe(true)
  })

  it('validates required secrets and submits editor payloads without exposing them in the list', async () => {
    const apiFetch = vi.fn(async (url, options = {}) => {
      if (url === '/session/notification-channel-kinds') return jsonResponse(CHANNEL_KIND_CONTRACT)
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
    const showToast = vi.fn()
    const { openNotificationChannelEditor, msg } = loadNotificationChannels({ apiFetch, showConfirm, showToast })

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
    expect(showToast).toHaveBeenCalledWith('Notification channel added.', 'success')
    expect(msg.textContent).toBe('')
  })

  it('renders channel actions and routes test, deliveries, mute, and delete requests', async () => {
    let channels = [{
      id: 'ntc_chat',
      kind: 'telegram',
      label: 'Ops chat',
      config: { chat_id: '12345' },
      triggers: ['run_complete', 'watcher_error'],
      muted: false,
      secret_fields: [{ name: 'bot_token', configured: true }],
    }]
    let testFails = false
    let deliveries = [
      {
        id: 'nte_existing',
        channel_id: 'ntc_chat',
        trigger: 'watcher_error',
        status: 'dead',
        attempts: 3,
        created: '2026-05-22T07:00:00+00:00',
        last_attempt_at: '2026-05-22T07:01:00+00:00',
        next_attempt_at: '',
        last_error: 'provider rejected message',
        run_id: 'run_existing_delivery',
      },
    ]
    const apiFetch = vi.fn(async (url, options = {}) => {
      if (url === '/session/notification-channel-kinds') return jsonResponse(CHANNEL_KIND_CONTRACT)
      if (url === '/session/notification-channels') return jsonResponse({ channels })
      if (url === '/session/notification-events?channel_id=ntc_chat&limit=5') {
        return jsonResponse({ events: deliveries, total: deliveries.length, limit: 5, offset: 0, has_more: false })
      }
      if (url === '/session/notification-channels/ntc_chat/test') {
        if (testFails) {
          deliveries = [{
            id: 'nte_test_2',
            channel_id: 'ntc_chat',
            trigger: 'test',
            status: 'retry_wait',
            attempts: 1,
            created: '2026-05-22T07:11:00+00:00',
            last_attempt_at: '2026-05-22T07:11:00+00:00',
            next_attempt_at: '2026-05-22T07:12:00+00:00',
            last_error: 'timeout',
            run_id: '',
          }, ...deliveries]
          return jsonResponse({ queued: 1, events: [{ event_id: 'nte_test_2', status: 'retry_wait', last_error: 'timeout' }] })
        }
        deliveries = [{
          id: 'nte_test',
          channel_id: 'ntc_chat',
          trigger: 'test',
          status: 'sent',
          attempts: 1,
          created: '2026-05-22T07:10:00+00:00',
          last_attempt_at: '2026-05-22T07:10:00+00:00',
          next_attempt_at: '',
          last_error: '',
          run_id: '',
        }, ...deliveries]
        return jsonResponse({ queued: 1, events: [{ event_id: 'nte_test', status: 'sent', last_error: '' }] })
      }
      if (url === '/session/notification-channels/ntc_chat' && options.method === 'PATCH') {
        const body = JSON.parse(options.body)
        channels = [{
          ...channels[0],
          label: body.label,
          config: body.config,
          triggers: body.triggers,
          muted: body.muted,
        }]
        return jsonResponse({ channel: channels[0] })
      }
      if (url === '/session/notification-channels/ntc_chat' && options.method === 'DELETE') {
        channels = []
        return jsonResponse({ removed: true })
      }
      throw new Error(`unexpected request ${url}`)
    })
    const showConfirm = vi.fn(async (options) => {
      const saveAction = options.actions?.find(action => action.id === 'save')
      if (saveAction) {
        options.content.querySelector('input[placeholder="Label"]').value = 'Ops chat edited'
        return saveAction.onActivate()
      }
      return 'delete'
    })
    const showToast = vi.fn()
    const { list, msg, refreshNotificationChannels } = loadNotificationChannels({ apiFetch, showConfirm, showToast })

    await refreshNotificationChannels({ force: true })
    expect(list.textContent).toContain('Ops chat')
    expect(list.textContent).toContain('run complete, watcher error · chat 12345')

    Array.from(list.querySelectorAll('button')).find(button => button.textContent === 'Deliveries').click()
    await vi.waitFor(() => expect(list.textContent).toContain('Recent deliveries'))
    expect(list.textContent).toContain('watcher error')
    await vi.waitFor(() => expect(list.textContent).toContain('provider rejected message'))
    expect(apiFetch).toHaveBeenCalledWith('/session/notification-events?channel_id=ntc_chat&limit=5')

    Array.from(list.querySelectorAll('button')).find(button => button.textContent === 'Test').click()
    await vi.waitFor(() => expect(showToast).toHaveBeenCalledWith('Test notification delivered.', 'success'))
    expect(msg.textContent).toBe('')
    await vi.waitFor(() => expect(list.textContent).toContain('sent'))

    testFails = true
    Array.from(list.querySelectorAll('button')).find(button => button.textContent === 'Test').click()
    await vi.waitFor(() => expect(showToast).toHaveBeenCalledWith('Test notification failed: timeout', 'error'))
    expect(msg.textContent).toBe('')
    await vi.waitFor(() => expect(list.textContent).toContain('retry wait'))

    Array.from(list.querySelectorAll('button')).find(button => button.textContent === 'Edit').click()
    await vi.waitFor(() => expect(showToast).toHaveBeenCalledWith('Notification channel updated.', 'success'))
    expect(list.textContent).toContain('Ops chat edited')
    expect(msg.textContent).toBe('')

    Array.from(list.querySelectorAll('button')).find(button => button.textContent === 'Mute').click()
    await vi.waitFor(() => expect(showToast).toHaveBeenCalledWith('Notification channel muted.', 'success'))
    expect(msg.textContent).toBe('')
    expect(JSON.parse(apiFetch.mock.calls.slice().reverse().find(([url, options]) => (
      url === '/session/notification-channels/ntc_chat' && options?.method === 'PATCH'
    ))[1].body).muted).toBe(true)

    Array.from(list.querySelectorAll('button')).find(button => button.textContent === 'Delete').click()
    await vi.waitFor(() => expect(showToast).toHaveBeenCalledWith('Notification channel deleted.', 'success'))
    expect(msg.textContent).toBe('')
    expect(showConfirm).toHaveBeenCalledWith(expect.objectContaining({ tone: 'danger' }))
    expect(list.textContent).toContain('No notification channels yet.')
  })
})
