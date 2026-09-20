// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createOperatorAccess } from '../../../app/static/js/features/admin/operator_access.js';
import { initialize as initializeRefresh } from '../../../app/static/js/features/diagnostics/refresh.js';

const response = (status, body = {}) => ({ status, ok: status < 400, headers: new Headers(),
  json: async () => body, text: async () => JSON.stringify(body), clone: () => response(status, body) });

beforeEach(() => {
  document.body.innerHTML = '<main><p>PRIVATE_DIAGNOSTICS</p><input value="PRIVATE_FILTER"></main><div class="diag-refreshed-at">now</div>';
});
afterEach(() => { document.cookie = 'darklab_csrf=; Max-Age=0; Path=/'; vi.useRealTimers(); });

describe('operator page access', () => {
  it.each([401, 403, 404])('clears data, stops requests and validates the destination after %s', async status => {
    const navigate = vi.fn();
    const fetcher = vi.fn(async () => response(status, { error: 'reauthentication_required', destination: '/admin/reauth?next=%2Fdiag' }));
    const access = createOperatorAccess({ fetcher, navigate });
    await expect(access.fetch('/diag')).rejects.toThrow();
    expect(document.body.innerHTML).not.toContain('PRIVATE');
    expect(document.querySelector('.diag-refreshed-at').textContent).toBe('');
    expect(access.active).toBe(false);
    await expect(access.fetch('/diag')).rejects.toThrow();
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(navigate).toHaveBeenCalledWith('/admin/reauth?next=%2Fdiag');
  });

  it.each(['https://elsewhere.test/admin/reauth', '//elsewhere.test/auth/sign-in', '/diag/ai-test', 'javascript:alert(1)'])(
    'never navigates to an unapproved destination %s', async destination => {
      const navigate = vi.fn();
      const access = createOperatorAccess({ navigate, fetcher: async () => response(401, { destination }) });
      await expect(access.fetch('/diag')).rejects.toThrow();
      expect(navigate).not.toHaveBeenCalled();
      expect(document.querySelector('main a')).toBeNull();
    },
  );

  it('does not expose a late body after another request loses access', async () => {
    let finish;
    const pendingBody = new Promise(resolve => { finish = resolve; });
    const fetcher = vi.fn().mockResolvedValueOnce({ ...response(200), json: () => pendingBody })
      .mockResolvedValueOnce(response(404));
    const access = createOperatorAccess({ fetcher });
    const first = await access.fetch('/diag?format=json');
    const body = first.json();
    await expect(access.fetch('/admin/access')).rejects.toThrow();
    finish({ secret: 'must not render' });
    await expect(body).rejects.toThrow();
  });

  it('adds the CSRF cookie only to mutations and refuses automatic HTTP redirects', async () => {
    document.cookie = 'darklab_csrf=safe-token; Path=/';
    const fetcher = vi.fn(async () => response(200));
    const access = createOperatorAccess({ fetcher });
    await access.fetch('/diag/ai-test', { method: 'POST' });
    await access.fetch('/diag/classifier-inspector');
    expect(fetcher.mock.calls[0][1].headers.get('X-Darklab-CSRF')).toBe('safe-token');
    expect(fetcher.mock.calls[1][1].headers.has('X-Darklab-CSRF')).toBe(false);
    expect(fetcher.mock.calls[0][1].redirect).toBe('error');
    expect(fetcher.mock.calls[0][1].headers.get('X-Requested-With')).toBe('XMLHttpRequest');
  });

  it('clears on authentication storage failure but keeps access after a provider outage', async () => {
    const access = createOperatorAccess({ fetcher: vi.fn().mockResolvedValueOnce(response(503, { error: 'ai_unavailable' }))
      .mockResolvedValueOnce(response(503, { error: 'operator_access_unavailable' })) });
    expect((await access.fetch('/diag/ai-test')).status).toBe(503);
    expect(access.active).toBe(true);
    await expect(access.fetch('/admin/access')).rejects.toThrow();
    expect(access.active).toBe(false);
  });

  it('clears the current diagnostics snapshot after a successful automatic refresh', async () => {
    vi.useFakeTimers();
    const root = document.querySelector('main');
    root.className = 'diag-main';
    const fetcher = vi.fn().mockResolvedValueOnce({ ...response(200),
      text: async () => '<main class="diag-main"><p>NEW_PRIVATE_SNAPSHOT</p></main>' })
      .mockResolvedValueOnce(response(404));
    const access = createOperatorAccess({ fetcher });
    initializeRefresh(access);
    await vi.advanceTimersByTimeAsync(10000);
    expect(document.querySelector('main')).toBe(root);
    expect(root.textContent).toBe('NEW_PRIVATE_SNAPSHOT');
    await expect(access.fetch('/admin/access')).rejects.toThrow();
    expect(document.body.innerHTML).not.toContain('PRIVATE');
    await vi.advanceTimersByTimeAsync(30000);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('stops the periodic authorization check after losing access', async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn(async () => response(404));
    const access = createOperatorAccess({ fetcher });
    access.start();
    await vi.advanceTimersByTimeAsync(10000);
    expect(access.active).toBe(false);
    await vi.advanceTimersByTimeAsync(30000);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
