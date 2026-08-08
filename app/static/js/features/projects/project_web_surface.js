// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Project Web Surface gallery controller.
// Loaded on demand when the Project workspace opens the Web Surface tab.

let exportedDarklabProjectWebSurface = null;

(function projectWebSurfaceModule(global) {
  'use strict';

  const IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);

  function createProjectWebSurfaceController(context) {
    const ctx = context || {};
    const pages = new Map();
    const thumbnailUrls = new Map();
    const thumbnailPromises = new Map();
    const pageLimit = Math.max(1, Number(ctx.pageLimit || 24));

    function page(projectId) {
      const key = String(projectId || '');
      if (!pages.has(key)) {
        pages.set(key, {
          captures: [],
          total: 0,
          limit: pageLimit,
          offset: 0,
          loading: false,
          loaded: false,
          error: '',
        });
      }
      return pages.get(key);
    }

    function setPageOffset(projectId, offset) {
      page(projectId).offset = Math.max(0, Number(offset || 0));
    }

    function rerender() {
      ctx.renderProjectExplorer?.();
      if (ctx.mobileView?.() === 'detail') ctx.renderProjectMobileDetail?.();
    }

    async function load(projectId, options = {}) {
      const normalizedProjectId = String(projectId || '');
      if (!normalizedProjectId) return page(normalizedProjectId);
      const state = page(normalizedProjectId);
      const offset = Math.max(0, Number(options.offset ?? state.offset ?? 0));
      if (state.loading && offset === state.offset) return state;
      state.loading = true;
      state.error = '';
      state.offset = offset;
      if (!options.skipInitialRender) rerender();
      try {
        const params = new URLSearchParams({
          limit: String(state.limit),
          offset: String(offset),
        });
        const resp = await ctx.apiFetch(
          `/projects/${encodeURIComponent(normalizedProjectId)}/web-surface?${params.toString()}`,
          { cache: 'no-store' },
        );
        if (!resp.ok) throw await ctx.projectResponseError(resp, 'Could not load the Web Surface.');
        const data = await resp.json();
        if (state.offset !== offset) return state;
        state.captures = Array.isArray(data.captures) ? data.captures : [];
        state.total = Math.max(0, Number(data.total || 0));
        state.limit = Math.max(1, Number(data.limit || state.limit));
        state.loaded = true;
      } catch (err) {
        if (state.offset === offset) {
          state.captures = [];
          state.total = 0;
          state.loaded = true;
          state.error = err?.message || 'Could not load the Web Surface.';
        }
        ctx.logClientError?.('failed to load project Web Surface', err, {
          project_id: normalizedProjectId,
        });
      } finally {
        if (state.offset === offset) state.loading = false;
        if (!options.skipFinalRender) rerender();
      }
      return state;
    }

    function thumbnailKey(projectId, artifact) {
      return [projectId, artifact?.id, artifact?.content_sha256].map(value => String(value || '')).join('\x1f');
    }

    function releaseThumbnail(key) {
      const url = thumbnailUrls.get(key);
      if (url && typeof URL?.revokeObjectURL === 'function') URL.revokeObjectURL(url);
      thumbnailUrls.delete(key);
      thumbnailPromises.delete(key);
    }

    function invalidate(projectId = '') {
      const normalizedProjectId = String(projectId || '');
      if (normalizedProjectId) pages.delete(normalizedProjectId);
      else pages.clear();
      [...thumbnailUrls.keys()].forEach((key) => {
        if (!normalizedProjectId || key.startsWith(`${normalizedProjectId}\x1f`)) releaseThumbnail(key);
      });
    }

    async function fetchThumbnail(projectId, capture) {
      const artifact = capture?.artifact || {};
      const key = thumbnailKey(projectId, artifact);
      if (thumbnailUrls.has(key)) return thumbnailUrls.get(key);
      if (thumbnailPromises.has(key)) return thumbnailPromises.get(key);
      const promise = (async () => {
        const resp = await ctx.apiFetch(
          `/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifact.id)}/download`,
          { cache: 'no-store' },
        );
        if (!resp.ok) throw await ctx.projectResponseError(resp, 'Screenshot preview is unavailable.');
        const blob = await resp.blob();
        const contentType = String(blob.type || artifact.content_type || '').split(';', 1)[0].toLowerCase();
        if (!IMAGE_TYPES.has(contentType)) throw new Error('Screenshot preview returned an unsupported image type.');
        if (typeof URL?.createObjectURL !== 'function') throw new Error('Screenshot preview is unavailable in this browser.');
        const url = URL.createObjectURL(blob);
        thumbnailUrls.set(key, url);
        return url;
      })().finally(() => thumbnailPromises.delete(key));
      thumbnailPromises.set(key, promise);
      return promise;
    }

    function statusLabel(capture) {
      const state = String(capture?.capture_state || 'unavailable');
      if (state === 'current') return 'current';
      if (state === 'changed') return 'file changed';
      if (state === 'metadata_conflict') return 'metadata conflict';
      if (state === 'metadata_missing') return 'metadata missing';
      return 'unavailable';
    }

    function statusTone(capture) {
      const state = String(capture?.capture_state || 'unavailable');
      if (state === 'current') return 'is-current';
      if (state === 'changed') return 'is-warning';
      return 'is-unavailable';
    }

    function placeholderText(capture) {
      const state = String(capture?.capture_state || 'unavailable');
      if (state === 'changed') return 'The saved file changed after capture.';
      if (state === 'metadata_conflict') return 'Conflicting capture metadata was rejected.';
      if (state === 'metadata_missing') return 'Capture metadata is no longer available.';
      return capture?.artifact?.file_status_detail || 'Screenshot file is unavailable.';
    }

    function captureTitle(capture) {
      return String(capture?.title || capture?.url || capture?.artifact?.display_name || 'Web capture');
    }

    function metaLine(capture) {
      const parts = [];
      if (Number.isFinite(Number(capture?.status_code)) && Number(capture.status_code) > 0) {
        parts.push(`HTTP ${Number(capture.status_code)}`);
      }
      const technologies = Array.isArray(capture?.technologies) ? capture.technologies.filter(Boolean) : [];
      if (technologies.length) parts.push(technologies.slice(0, 4).join(', '));
      if (capture?.profile_role) parts.push(`role: ${capture.profile_role}`);
      return parts.join(ctx.metaSeparator || ' · ');
    }

    function makeAction(label, handler, className = '') {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `btn btn-ghost btn-compact project-web-surface-action${className ? ` ${className}` : ''}`;
      button.textContent = label;
      button.addEventListener('click', handler);
      ctx.bindProjectRuntimePressable?.(button);
      return button;
    }

    function renderPreview(projectId, capture, card) {
      const preview = document.createElement('button');
      preview.type = 'button';
      preview.className = 'project-web-surface-preview';
      preview.setAttribute('aria-label', `Expand screenshot for ${captureTitle(capture)}`);
      preview.setAttribute('aria-expanded', 'false');
      ctx.bindProjectRuntimePressable?.(preview);
      const image = document.createElement('img');
      image.className = 'project-web-surface-image u-hidden';
      image.alt = `Screenshot of ${String(capture?.url || captureTitle(capture))}`;
      image.loading = 'lazy';
      const placeholder = document.createElement('span');
      placeholder.className = 'project-web-surface-placeholder';
      placeholder.textContent = String(capture?.capture_state || '') === 'current'
        ? 'Loading screenshot...'
        : placeholderText(capture);
      preview.append(image, placeholder);
      preview.addEventListener('click', () => {
        if (image.classList.contains('u-hidden')) return;
        const expanded = !card.classList.contains('is-expanded');
        card.classList.toggle('is-expanded', expanded);
        preview.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        preview.setAttribute('aria-label', `${expanded ? 'Fit' : 'Expand'} screenshot for ${captureTitle(capture)}`);
      });
      if (String(capture?.capture_state || '') === 'current' && capture?.artifact?.file_available) {
        fetchThumbnail(projectId, capture).then((url) => {
          if (!image.isConnected) return;
          image.src = url;
          image.classList.remove('u-hidden');
          placeholder.classList.add('u-hidden');
        }).catch((err) => {
          placeholder.textContent = 'Screenshot preview is unavailable.';
          ctx.logClientError?.('failed to load Web Surface thumbnail', err, {
            project_id: String(projectId || ''),
            artifact_id: String(capture?.artifact?.id || ''),
          });
        });
      }
      return preview;
    }

    function renderCard(projectId, capture) {
      const card = document.createElement('article');
      card.className = 'project-web-surface-card panel-row';
      card.appendChild(renderPreview(projectId, capture, card));
      const body = document.createElement('div');
      body.className = 'project-web-surface-card-body';
      const head = document.createElement('div');
      head.className = 'project-web-surface-card-head';
      const title = document.createElement('h3');
      title.className = 'project-web-surface-title';
      title.textContent = captureTitle(capture);
      const status = document.createElement('span');
      status.className = `badge project-web-surface-status ${statusTone(capture)}`;
      status.textContent = statusLabel(capture);
      head.append(title, status);
      body.appendChild(head);
      if (capture?.url) {
        const url = document.createElement('div');
        url.className = 'project-web-surface-url';
        url.textContent = String(capture.url);
        body.appendChild(url);
      }
      const metadata = metaLine(capture);
      if (metadata) {
        const meta = document.createElement('div');
        meta.className = 'project-web-surface-meta';
        meta.textContent = metadata;
        body.appendChild(meta);
      }
      const source = document.createElement('div');
      source.className = 'project-web-surface-meta';
      source.textContent = [
        capture?.captured_at ? `captured ${ctx.formatDate?.(capture.captured_at) || capture.captured_at}` : '',
        capture?.source_run?.id ? `run ${ctx.shortProjectRunId?.(capture.source_run.id) || capture.source_run.id}` : '',
      ].filter(Boolean).join(ctx.metaSeparator || ' · ');
      if (source.textContent) body.appendChild(source);
      const actions = document.createElement('div');
      actions.className = 'project-web-surface-actions';
      if (capture?.url_entity_id && capture?.url) {
        actions.appendChild(makeAction('Open URL in Atlas', () => {
          ctx.openEntityInAtlas?.(projectId, {
            id: capture.url_entity_id,
            type: 'url',
            canonical_value: capture.url,
          });
        }));
      }
      if (capture?.source_run?.id) {
        actions.appendChild(makeAction('Run details', () => {
          ctx.closeProjectWorkspace?.({ refocus: false });
          ctx.openHistoryRunDetails?.({
            id: String(capture.source_run.id),
            command: String(capture.source_run.command || ''),
          });
        }));
      }
      if (actions.childElementCount) body.appendChild(actions);
      card.appendChild(body);
      return card;
    }

    function renderPagination(projectId, state, position) {
      if (state.total <= state.limit && state.offset === 0) return null;
      const wrap = document.createElement('div');
      wrap.className = 'project-workspace-pagination project-web-surface-pagination';
      wrap.dataset.projectWebSurfacePagerPosition = position;
      const summary = document.createElement('div');
      summary.className = 'project-workspace-pagination-summary';
      summary.textContent = `${state.total ? state.offset + 1 : 0}-${Math.min(state.total, state.offset + state.limit)} of ${state.total} captures`;
      const controls = document.createElement('div');
      controls.className = 'project-workspace-pagination-controls';
      const previous = makeAction('Previous', () => changePage(projectId, state.offset - state.limit));
      previous.disabled = state.loading || state.offset <= 0;
      const label = document.createElement('span');
      label.className = 'project-workspace-pagination-status';
      label.textContent = state.loading ? 'Loading...' : `Page ${Math.floor(state.offset / state.limit) + 1}`;
      const next = makeAction('Next', () => changePage(projectId, state.offset + state.limit));
      next.disabled = state.loading || state.offset + state.limit >= state.total;
      controls.append(previous, label, next);
      wrap.append(summary, controls);
      return wrap;
    }

    async function changePage(projectId, offset) {
      setPageOffset(projectId, offset);
      await load(projectId, { offset: page(projectId).offset });
    }

    function render(container, projectId) {
      const state = page(projectId);
      if (!state.loaded && !state.loading) load(projectId).catch(() => {});
      if (state.loading && !state.captures.length) {
        container.appendChild(ctx.emptyProjectPanel('Loading Web Surface captures...'));
        return;
      }
      if (state.error && !state.captures.length) {
        container.appendChild(ctx.emptyProjectPanel(state.error));
        return;
      }
      if (state.loaded && !state.total) {
        container.appendChild(ctx.emptyProjectPanel(
          'No HTTPx screenshots are linked to this project yet. Run a screenshot-enabled HTTP assessment to build the gallery.',
        ));
        return;
      }
      const intro = document.createElement('div');
      intro.className = 'project-web-surface-intro';
      intro.textContent = 'Review saved HTTP screenshots without loading captured pages in the app origin.';
      container.appendChild(intro);
      const topPager = renderPagination(projectId, state, 'top');
      if (topPager) container.appendChild(topPager);
      const gallery = document.createElement('div');
      gallery.className = 'project-web-surface-grid';
      state.captures.forEach(capture => gallery.appendChild(renderCard(projectId, capture)));
      container.appendChild(gallery);
      const bottomPager = renderPagination(projectId, state, 'bottom');
      if (bottomPager) container.appendChild(bottomPager);
    }

    function dispose() {
      invalidate();
    }

    global?.addEventListener?.('pagehide', dispose, { once: true });

    return {
      dispose,
      invalidate,
      load,
      page,
      render,
      setPageOffset,
    };
  }

  const DarklabProjectWebSurface = { createProjectWebSurfaceController };
  exportedDarklabProjectWebSurface = DarklabProjectWebSurface;
})(globalThis);

export {
  exportedDarklabProjectWebSurface as DarklabProjectWebSurface,
};
