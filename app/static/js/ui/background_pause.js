// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Keep suspension explanations consistent across background-work controls.
function backgroundPauseMessage(reason) {
  if (reason === 'principal_disabled') return 'Paused by an operator action. Review this work before resuming it.';
  if (/revok/i.test(String(reason || ''))) return 'Paused because its originating access credential was revoked.';
  return '';
}

export { backgroundPauseMessage };
