export const DESKTOP_VISUAL_CONTRACT = {
  name: 'desktop',
  viewport: { width: 1600, height: 900 },
  deviceScaleFactor: 2,
  hasTouch: false,
  userAgentIncludes: null,
  mobileTerminalMode: false,
}

export const MOBILE_VISUAL_CONTRACT = {
  name: 'mobile',
  viewport: { width: 430, height: 932 },
  deviceScaleFactor: 3,
  hasTouch: true,
  userAgentIncludes: 'iPhone',
  mobileTerminalMode: true,
}

export const CAPTURE_SESSION_TOKEN = 'tok_cafebabecafebabecafebabecafebabe'
export const VISUAL_HISTORY_FIXTURE_NAME = 'visual-flows'
export const VISUAL_HISTORY_MIN_RUNS = 240
export const VISUAL_HISTORY_MIN_ROOTS = 12
export const CAPTURE_SEEDED_HISTORY_MIN_RUNS = VISUAL_HISTORY_MIN_RUNS
export const CAPTURE_SEEDED_HISTORY_MIN_ROOTS = VISUAL_HISTORY_MIN_ROOTS
