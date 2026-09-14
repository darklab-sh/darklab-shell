// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { apiFetch } from '../../session.js';

function failure(stage, reason, status, level) {
  return { ok: false, stage, reason, status, level };
}

async function loadOIDCIdentity() {
  let response;
  try {
    response = await apiFetch('/auth/oidc/identity', { cache: 'no-store' });
  } catch (error) {
    const network = ['TypeError', 'NetworkError', 'AbortError'].includes(error?.name);
    return failure('request', network ? 'network_unavailable' : 'client_failed', 0, network ? 'warning' : 'error');
  }
  const status = Number.isInteger(response?.status) && response.status >= 100 && response.status <= 599
    ? response.status : 0;
  if (status === 404) return { ok: false, disabled: true };
  if (!response?.ok) {
    return failure('response', status >= 500 ? 'server_failed' : 'request_rejected', status, status >= 500 || !status ? 'error' : 'warning');
  }
  let data;
  try {
    data = await response.json();
  } catch (_) {
    return failure('parse', 'invalid_json', status, 'error');
  }
  if (!data || Array.isArray(data) || typeof data.linked !== 'boolean') {
    return failure('response', 'invalid_payload', status, 'error');
  }
  return { ok: true, linked: data.linked };
}

export { loadOIDCIdentity };
