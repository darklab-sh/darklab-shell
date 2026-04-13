import { fromDomScript } from './helpers/extract.js'

describe('frontend config defaults', () => {
  it('includes the welcome timing keys exposed by /config', () => {
    const { APP_CONFIG } = fromDomScript(
      'app/static/js/config.js',
      {},
      'APP_CONFIG',
    )

    expect(APP_CONFIG).toMatchObject({
      app_name: expect.any(String),
      prompt_prefix: expect.any(String),
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
  })

  it('keeps the built-in share redaction baseline in bootstrap defaults', () => {
    const { APP_CONFIG } = fromDomScript(
      'app/static/js/config.js',
      {},
      'APP_CONFIG',
    )

    expect(APP_CONFIG.share_redaction_enabled).toBe(true)
    expect(APP_CONFIG.share_redaction_rules.some(rule => rule.label === 'bearer token')).toBe(true)
    expect(APP_CONFIG.share_redaction_rules.some(rule => rule.label === 'email address')).toBe(true)
  })
})
