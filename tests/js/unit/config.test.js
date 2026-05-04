import { readFileSync } from 'fs'
import { resolve } from 'path'
import { fromDomScript } from './helpers/extract.js'

const CONFIG_SRC = readFileSync(resolve(process.cwd(), 'app/static/js/config.js'), 'utf8')

describe('frontend config bootstrap', () => {
  it('reads APP_CONFIG from the server-rendered bootstrap JSON', () => {
    const bootstrap = {
      app_name: 'darklab_shell',
      prompt_username: 'anon',
      prompt_domain: 'darklab.sh',
      recent_commands_limit: 50,
      welcome_char_ms: 18,
      welcome_jitter_ms: 12,
      welcome_post_cmd_ms: 650,
      welcome_inter_block_ms: 850,
      welcome_first_prompt_idle_ms: 1500,
      welcome_post_status_pause_ms: 500,
      welcome_sample_count: 5,
      welcome_status_labels: ['CONFIG', 'RUNNER', 'HISTORY', 'LIMITS', 'AUTOCOMPLETE'],
      welcome_hint_interval_ms: 4200,
      welcome_hint_rotations: 0,
      share_redaction_enabled: true,
      share_redaction_rules: [{ label: 'bearer token' }],
    }
    const document = {
      getElementById: (id) => id === 'app-config-json'
        ? { textContent: JSON.stringify(bootstrap) }
        : null,
    }
    const window = {}
    const { APP_CONFIG } = fromDomScript('app/static/js/config.js', { document, window }, 'APP_CONFIG')

    expect(APP_CONFIG).toMatchObject({
      app_name: expect.any(String),
      prompt_username: expect.any(String),
      prompt_domain: expect.any(String),
      welcome_char_ms: expect.any(Number),
      welcome_jitter_ms: expect.any(Number),
      welcome_post_cmd_ms: expect.any(Number),
      welcome_inter_block_ms: expect.any(Number),
      welcome_first_prompt_idle_ms: expect.any(Number),
      welcome_post_status_pause_ms: expect.any(Number),
      welcome_sample_count: expect.any(Number),
      welcome_status_labels: expect.any(Array),
      welcome_hint_interval_ms: expect.any(Number),
      welcome_hint_rotations: expect.any(Number),
      share_redaction_enabled: expect.any(Boolean),
      share_redaction_rules: expect.any(Array),
    })
    expect(APP_CONFIG).toEqual(bootstrap)
    expect(window.APP_CONFIG).toBe(APP_CONFIG)
  })

  it('falls back to an existing window APP_CONFIG object for non-template harnesses', () => {
    const bootstrap = { app_name: 'harness', recent_commands_limit: 3 }
    const document = { getElementById: () => null }
    const window = { APP_CONFIG: bootstrap }
    const { APP_CONFIG } = fromDomScript('app/static/js/config.js', { document, window }, 'APP_CONFIG')

    expect(APP_CONFIG).toBe(bootstrap)
  })

  it('does not hard-code server config defaults in config.js', () => {
    const forbiddenFragments = [
      'DEFAULT_SHARE_REDACTION_RULES',
      "app_name: '",
      'recent_commands_limit:',
      'max_output_lines:',
      'max_tabs:',
      'history_panel_limit:',
      'command_timeout_seconds:',
      'welcome_char_ms:',
      'welcome_status_labels:',
    ]

    forbiddenFragments.forEach((fragment) => {
      expect(CONFIG_SRC).not.toContain(fragment)
    })
  })
})
