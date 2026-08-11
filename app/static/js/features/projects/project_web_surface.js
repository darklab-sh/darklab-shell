// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Project Web Surface gallery controller.
// Loaded on demand when the Project workspace opens the Web Surface tab.

let exportedDarklabProjectWebSurface = null;

(function projectWebSurfaceModule(global) {
  'use strict';

  const IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);
  const FILTER_FIELDS = [
    { name: 'target', label: 'Target', placeholder: 'Hostname or URL', type: 'search' },
    {
      name: 'status_code',
      label: 'HTTP status',
      placeholder: '200',
      inputMode: 'numeric',
      maxLength: 3,
      pattern: '[1-5][0-9]{2}',
    },
    { name: 'technology', label: 'Technology', placeholder: 'nginx' },
    { name: 'profile_role', label: 'HTTP role', placeholder: 'authenticated' },
    { name: 'visual_hash', label: 'Visual hash', placeholder: 'Exact hash' },
    {
      name: 'change_state',
      label: 'Change',
      options: [
        ['', 'Any comparison'],
        ['changed', 'Visual changed'],
        ['unchanged', 'Visual unchanged'],
        ['no_baseline', 'No baseline'],
        ['incomparable', 'Could not compare'],
        ['unknown', 'Outside comparison window'],
      ],
    },
  ];
  const GROUP_OPTIONS = [
    ['none', 'No grouping'],
    ['target', 'Group by target'],
    ['status', 'Group by HTTP status'],
    ['technology', 'Group by technology'],
    ['profile_role', 'Group by HTTP role'],
    ['visual_hash', 'Group by visual hash'],
    ['change_state', 'Group by change'],
  ];

  function emptyFilters() {
    return Object.fromEntries(FILTER_FIELDS.map(({ name }) => [name, '']));
  }

  function createProjectWebSurfaceController(context) {
    const ctx = context || {};
    const pages = new Map();
    const thumbnailUrls = new Map();
    const thumbnailPromises = new Map();
    const pageLimit = Math.max(1, Number(ctx.pageLimit || 24));
    let viewerOverlay = null;
    let viewerCard = null;
    let viewerTitle = null;
    let viewerMeta = null;
    let viewerBody = null;
    let viewerImage = null;
    let viewerPlaceholder = null;
    let viewerPrevious = null;
    let viewerNext = null;
    let viewerPosition = null;
    let viewerState = null;
    let viewerReturnFocus = null;
    let viewerRequestId = 0;
    let viewerDismissible = null;
    let viewerFocusTrap = null;
    let viewerTouchStart = null;

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
          filters: emptyFilters(),
          groupBy: 'none',
          candidateTotal: 0,
          candidateLimit: 200,
          candidateTruncated: false,
          comparisonCandidateLimit: 200,
          comparisonCandidateTruncated: false,
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
        FILTER_FIELDS.forEach(({ name }) => {
          const value = String(state.filters?.[name] || '').trim();
          if (value) params.set(name, value);
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
        state.candidateTotal = Math.max(0, Number(data.candidate_total || state.total));
        state.candidateLimit = Math.max(1, Number(data.candidate_limit || 200));
        state.candidateTruncated = Boolean(data.candidate_truncated);
        state.comparisonCandidateLimit = Math.max(1, Number(data.comparison_candidate_limit || 200));
        state.comparisonCandidateTruncated = Boolean(data.comparison_candidate_truncated);
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
      if (!normalizedProjectId || viewerState?.projectId === normalizedProjectId) {
        closeViewer({ restoreFocus: false });
      }
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
      if (state === 'current') return 'badge-tone-green';
      if (state === 'changed') return 'badge-tone-amber';
      return 'badge-tone-muted';
    }

    function placeholderText(capture) {
      const state = String(capture?.capture_state || 'unavailable');
      if (state === 'changed') return 'The saved file changed after capture.';
      if (state === 'metadata_conflict') return 'Conflicting capture metadata was rejected.';
      if (state === 'metadata_missing') return 'Capture metadata is no longer available.';
      return capture?.artifact?.file_status_detail || 'Screenshot file is unavailable.';
    }

    function captureIsViewable(capture) {
      return String(capture?.capture_state || '') === 'current' && Boolean(capture?.artifact?.file_available);
    }

    function captureTitle(capture) {
      return String(capture?.title || capture?.url || capture?.artifact?.display_name || 'Web capture');
    }

    function filtersActive(state) {
      return FILTER_FIELDS.some(({ name }) => String(state.filters?.[name] || '').trim());
    }

    function groupLabel(capture, groupBy) {
      if (groupBy === 'target') {
        try {
          return new URL(String(capture?.url || '')).hostname || 'Unknown target';
        } catch (_err) {
          return String(capture?.url || 'Unknown target');
        }
      }
      if (groupBy === 'status') {
        const statusCode = Number(capture?.status_code);
        return Number.isInteger(statusCode) && statusCode > 0 ? `HTTP ${statusCode}` : 'Unknown HTTP status';
      }
      if (groupBy === 'technology') {
        const technologies = Array.isArray(capture?.technologies) ? capture.technologies.filter(Boolean) : [];
        return technologies.length ? technologies.join(', ') : 'No detected technology';
      }
      if (groupBy === 'profile_role') return String(capture?.profile_role || 'No HTTP role');
      if (groupBy === 'visual_hash') return String(capture?.visual_hash || 'No visual hash');
      if (groupBy === 'change_state') return changeLabel(capture);
      return '';
    }

    function changeLabel(capture) {
      const state = String(capture?.comparison?.state || 'incomparable');
      if (state === 'changed') return 'Visual changed';
      if (state === 'unchanged') return 'Visual unchanged';
      if (state === 'no_baseline') return 'No baseline';
      if (state === 'unknown') return 'Outside comparison window';
      return 'Could not compare';
    }

    function changeTone(capture) {
      const state = String(capture?.comparison?.state || 'incomparable');
      if (state === 'changed') return 'badge-tone-amber';
      if (state === 'unchanged') return 'badge-tone-green';
      return 'badge-tone-muted';
    }

    function changeDetail(capture) {
      const comparison = capture?.comparison || {};
      const previous = comparison.previous_capture || {};
      const previousTime = previous.captured_at
        ? (ctx.formatDate?.(previous.captured_at) || previous.captured_at)
        : '';
      if (comparison.state === 'changed') return `Visual hash changed since ${previousTime || 'the previous capture'}.`;
      if (comparison.state === 'unchanged') return `Visual hash unchanged since ${previousTime || 'the previous capture'}.`;
      if (comparison.state === 'no_baseline') return 'No earlier capture has the same exact URL and HTTP role.';
      if (comparison.state === 'unknown') return 'An earlier baseline may fall outside the bounded comparison window.';
      return 'A compatible visual hash was not available for comparison.';
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
      preview.className = 'btn btn-ghost project-web-surface-preview';
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

    function closeViewer({ restoreFocus = true } = {}) {
      if (!viewerOverlay) return;
      viewerRequestId += 1;
      viewerState = null;
      viewerOverlay.setAttribute('aria-hidden', 'true');
      if (typeof ctx.hideModalOverlay === 'function') ctx.hideModalOverlay(viewerOverlay);
      else viewerOverlay.style.display = 'none';
      if (
        restoreFocus
        && viewerReturnFocus
        && viewerReturnFocus.isConnected
        && typeof ctx.focusElement === 'function'
      ) {
        const focusTarget = viewerReturnFocus;
        window.setTimeout(() => ctx.focusElement(focusTarget, { preventScroll: true }), 0);
      }
      viewerReturnFocus = null;
    }

    function moveViewer(delta) {
      if (!viewerState) return;
      const nextIndex = viewerState.index + Number(delta || 0);
      if (nextIndex < 0 || nextIndex >= viewerState.captures.length) return;
      viewerState.index = nextIndex;
      renderViewer();
    }

    function bindViewerTouch(body) {
      body.addEventListener('touchstart', (event) => {
        const touch = event.touches?.[0];
        viewerTouchStart = touch ? { x: touch.clientX, y: touch.clientY } : null;
      }, { passive: true });
      body.addEventListener('touchend', (event) => {
        const touch = event.changedTouches?.[0];
        const start = viewerTouchStart;
        viewerTouchStart = null;
        if (!touch || !start) return;
        const deltaX = touch.clientX - start.x;
        const deltaY = touch.clientY - start.y;
        if (Math.abs(deltaX) < 48 || Math.abs(deltaX) <= Math.abs(deltaY) * 1.25) return;
        moveViewer(deltaX < 0 ? 1 : -1);
      }, { passive: true });
      body.addEventListener('touchcancel', () => { viewerTouchStart = null; }, { passive: true });
    }

    function ensureViewer() {
      if (viewerOverlay) return viewerOverlay;
      viewerOverlay = document.createElement('div');
      viewerOverlay.id = 'project-web-surface-viewer-overlay';
      viewerOverlay.className = 'modal-overlay project-web-surface-viewer-overlay';
      viewerOverlay.setAttribute('aria-hidden', 'true');
      viewerCard = document.createElement('section');
      viewerCard.className = 'modal-card project-web-surface-viewer';
      viewerCard.setAttribute('role', 'dialog');
      viewerCard.setAttribute('aria-modal', 'true');
      viewerCard.setAttribute('aria-labelledby', 'project-web-surface-viewer-title');
      viewerCard.setAttribute('aria-describedby', 'project-web-surface-viewer-meta');
      const header = document.createElement('div');
      header.className = 'project-web-surface-viewer-header';
      viewerTitle = document.createElement('h2');
      viewerTitle.id = 'project-web-surface-viewer-title';
      const close = document.createElement('button');
      close.type = 'button';
      close.className = 'btn btn-ghost btn-icon-only btn-compact project-web-surface-viewer-close';
      close.setAttribute('aria-label', 'Close full screenshot view');
      close.title = 'Close full screenshot view';
      close.textContent = '×';
      header.append(viewerTitle, close);
      viewerBody = document.createElement('div');
      viewerBody.className = 'project-web-surface-viewer-body nice-scroll';
      viewerImage = document.createElement('img');
      viewerImage.className = 'project-web-surface-viewer-image u-hidden';
      viewerPlaceholder = document.createElement('div');
      viewerPlaceholder.className = 'project-web-surface-viewer-placeholder';
      viewerBody.append(viewerImage, viewerPlaceholder);
      bindViewerTouch(viewerBody);
      const footer = document.createElement('div');
      footer.className = 'project-web-surface-viewer-footer';
      viewerPrevious = makeAction('Previous', () => moveViewer(-1));
      viewerPrevious.classList.add('project-web-surface-viewer-previous');
      viewerPosition = document.createElement('span');
      viewerPosition.className = 'project-web-surface-viewer-position';
      viewerPosition.setAttribute('aria-live', 'polite');
      viewerNext = makeAction('Next', () => moveViewer(1));
      viewerNext.classList.add('project-web-surface-viewer-next');
      viewerMeta = document.createElement('div');
      viewerMeta.id = 'project-web-surface-viewer-meta';
      viewerMeta.className = 'project-web-surface-viewer-meta';
      footer.append(viewerPrevious, viewerPosition, viewerNext, viewerMeta);
      viewerCard.append(header, viewerBody, footer);
      viewerOverlay.appendChild(viewerCard);
      document.body.appendChild(viewerOverlay);
      viewerCard.addEventListener('keydown', (event) => {
        if (!viewerState || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
        if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
        event.preventDefault();
        moveViewer(event.key === 'ArrowRight' ? 1 : -1);
      });
      if (typeof ctx.bindDismissible === 'function') {
        viewerDismissible = ctx.bindDismissible(viewerOverlay, {
          level: 'modal',
          isOpen: () => Boolean(viewerState),
          onClose: () => closeViewer(),
          backdropEl: viewerOverlay,
          closeButtons: close,
        });
      } else {
        close.addEventListener('click', () => closeViewer());
        viewerOverlay.addEventListener('click', (event) => {
          if (event.target === viewerOverlay) closeViewer();
        });
      }
      if (typeof ctx.bindFocusTrap === 'function') viewerFocusTrap = ctx.bindFocusTrap(viewerCard);
      return viewerOverlay;
    }

    function renderViewer() {
      if (!viewerState || !viewerTitle || !viewerImage || !viewerPlaceholder) return;
      const capture = viewerState.captures[viewerState.index];
      if (!capture) return;
      const requestId = ++viewerRequestId;
      viewerTitle.textContent = captureTitle(capture);
      viewerMeta.textContent = [
        String(capture?.url || ''),
        metaLine(capture),
        capture?.captured_at ? `captured ${ctx.formatDate?.(capture.captured_at) || capture.captured_at}` : '',
      ].filter(Boolean).join(ctx.metaSeparator || ' · ');
      viewerPosition.textContent = `${viewerState.index + 1} of ${viewerState.captures.length}`;
      viewerPrevious.disabled = viewerState.index === 0;
      viewerNext.disabled = viewerState.index === viewerState.captures.length - 1;
      if (viewerBody) {
        viewerBody.scrollTop = 0;
        viewerBody.scrollLeft = 0;
      }
      viewerImage.classList.add('u-hidden');
      viewerImage.removeAttribute('src');
      viewerImage.alt = `Full screenshot of ${String(capture?.url || captureTitle(capture))}`;
      viewerPlaceholder.classList.remove('u-hidden');
      viewerPlaceholder.textContent = 'Loading full screenshot...';
      fetchThumbnail(viewerState.projectId, capture).then((url) => {
        if (!viewerState || requestId !== viewerRequestId || !viewerImage?.isConnected) return;
        viewerImage.src = url;
        viewerImage.classList.remove('u-hidden');
        viewerPlaceholder.classList.add('u-hidden');
      }).catch((err) => {
        if (!viewerState || requestId !== viewerRequestId) return;
        viewerPlaceholder.textContent = 'Full screenshot is unavailable.';
        ctx.logClientError?.('failed to load Web Surface full image', err, {
          project_id: String(viewerState.projectId || ''),
          artifact_id: String(capture?.artifact?.id || ''),
        });
      });
    }

    function openViewer(projectId, capture, returnFocus) {
      const captures = page(projectId).captures.filter(captureIsViewable);
      const artifactId = String(capture?.artifact?.id || '');
      const index = captures.findIndex(item => String(item?.artifact?.id || '') === artifactId);
      if (index < 0) return;
      const overlay = ensureViewer();
      viewerState = { projectId: String(projectId || ''), captures, index };
      viewerReturnFocus = returnFocus || document.activeElement;
      overlay.setAttribute('aria-hidden', 'false');
      if (typeof ctx.showModalOverlay === 'function') ctx.showModalOverlay(overlay);
      else overlay.style.display = 'flex';
      renderViewer();
      window.setTimeout(() => {
        if (!viewerState) return;
        const close = viewerCard?.querySelector('.project-web-surface-viewer-close');
        ctx.focusElement?.(close, { preventScroll: true });
        ctx.markInteractionSurfaceReady?.('project-web-surface-viewer', overlay, viewerCard);
      }, 0);
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
      const badges = document.createElement('div');
      badges.className = 'project-web-surface-badges';
      const comparison = document.createElement('span');
      comparison.className = `badge project-web-surface-status ${changeTone(capture)}`;
      comparison.textContent = changeLabel(capture);
      badges.append(status, comparison);
      head.append(title, badges);
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
      const change = document.createElement('div');
      change.className = 'project-web-surface-meta';
      change.textContent = changeDetail(capture);
      body.appendChild(change);
      const actions = document.createElement('div');
      actions.className = 'project-web-surface-actions';
      if (captureIsViewable(capture)) {
        const fullView = makeAction('Full view', () => openViewer(projectId, capture, fullView));
        actions.appendChild(fullView);
        if (ctx.canMutateProjects?.() !== false) {
          actions.appendChild(makeAction('Add to package', () => {
            ctx.openPackageWithArtifact?.(projectId, String(capture?.artifact?.id || ''));
          }));
          actions.appendChild(makeAction('Add to report', () => {
            ctx.openReportWithArtifact?.(projectId, capture?.artifact || {});
          }));
        }
      }
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

    function renderControls(projectId, state) {
      const form = document.createElement('form');
      form.className = 'project-web-surface-controls';
      form.setAttribute('aria-label', 'Filter and group Web Surface captures');
      FILTER_FIELDS.forEach((field) => {
        const label = document.createElement('label');
        label.className = 'project-web-surface-control';
        const text = document.createElement('span');
        text.textContent = field.label;
        const control = field.options ? document.createElement('select') : document.createElement('input');
        control.name = field.name;
        control.className = field.options ? 'form-select form-control-compact' : 'form-control form-control-compact';
        control.setAttribute('aria-label', `Filter Web Surface by ${field.label.toLowerCase()}`);
        if (field.options) {
          field.options.forEach(([value, optionLabel]) => {
            const option = document.createElement('option');
            option.value = value;
            option.textContent = optionLabel;
            option.selected = value === String(state.filters?.[field.name] || '');
            control.appendChild(option);
          });
        } else {
          control.type = field.type || 'text';
          control.value = String(state.filters?.[field.name] || '');
          control.placeholder = field.placeholder;
          if (field.inputMode) control.inputMode = field.inputMode;
          if (field.maxLength) control.maxLength = field.maxLength;
          if (field.pattern) control.pattern = field.pattern;
        }
        label.append(text, control);
        form.appendChild(label);
      });
      const groupLabelNode = document.createElement('label');
      groupLabelNode.className = 'project-web-surface-control';
      const groupText = document.createElement('span');
      groupText.textContent = 'Grouping';
      const group = document.createElement('select');
      group.className = 'form-select form-control-compact';
      group.setAttribute('aria-label', 'Group Web Surface captures');
      GROUP_OPTIONS.forEach(([value, label]) => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = label;
        option.selected = value === state.groupBy;
        group.appendChild(option);
      });
      group.addEventListener('change', () => {
        state.groupBy = GROUP_OPTIONS.some(([value]) => value === group.value) ? group.value : 'none';
        rerender();
      });
      groupLabelNode.append(groupText, group);
      form.appendChild(groupLabelNode);
      const actions = document.createElement('div');
      actions.className = 'project-web-surface-control-actions';
      const apply = makeAction('Apply filters', () => {});
      apply.type = 'submit';
      apply.classList.replace('btn-ghost', 'btn-primary');
      apply.disabled = state.loading;
      const clear = makeAction('Clear filters', () => {
        state.filters = emptyFilters();
        state.offset = 0;
        load(projectId, { offset: 0 }).catch(() => {});
      });
      clear.disabled = state.loading || !filtersActive(state);
      actions.append(apply, clear);
      form.appendChild(actions);
      form.addEventListener('submit', (event) => {
        event.preventDefault();
        state.filters = Object.fromEntries(FILTER_FIELDS.map(({ name }) => [
          name,
          String(form.elements.namedItem(name)?.value || '').trim(),
        ]));
        state.offset = 0;
        load(projectId, { offset: 0 }).catch(() => {});
      });
      return form;
    }

    function renderGallery(projectId, state) {
      if (state.groupBy === 'none') {
        const gallery = document.createElement('div');
        gallery.className = 'project-web-surface-grid';
        state.captures.forEach(capture => gallery.appendChild(renderCard(projectId, capture)));
        return gallery;
      }
      const groups = new Map();
      state.captures.forEach((capture) => {
        const label = groupLabel(capture, state.groupBy);
        if (!groups.has(label)) groups.set(label, []);
        groups.get(label).push(capture);
      });
      const collection = document.createElement('div');
      collection.className = 'project-web-surface-groups';
      groups.forEach((captures, label) => {
        const section = document.createElement('section');
        section.className = 'project-web-surface-group';
        const heading = document.createElement('h3');
        heading.textContent = `${label} (${captures.length})`;
        const gallery = document.createElement('div');
        gallery.className = 'project-web-surface-grid';
        captures.forEach(capture => gallery.appendChild(renderCard(projectId, capture)));
        section.append(heading, gallery);
        collection.appendChild(section);
      });
      return collection;
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
      const intro = document.createElement('div');
      intro.className = 'project-web-surface-intro';
      intro.textContent = 'Review saved HTTP screenshots without loading captured pages in the app origin.';
      container.appendChild(intro);
      if (ctx.canMutateProjects?.() !== false) {
        const handoff = document.createElement('div');
        handoff.className = 'project-web-surface-handoff-note';
        handoff.textContent = "Screenshot handoffs keep redaction explicit: package handoff starts in Raw because images can't be redacted automatically; choosing Redacted omits the image bytes. Reports include screenshot metadata, not the binary image.";
        container.appendChild(handoff);
      }
      container.appendChild(renderControls(projectId, state));
      if (state.candidateTruncated && filtersActive(state)) {
        const limited = document.createElement('div');
        limited.className = 'project-web-surface-limited';
        limited.setAttribute('role', 'status');
        limited.textContent = `Filters searched the newest ${state.candidateLimit} of ${state.candidateTotal} captures. Older captures weren't included.`;
        container.appendChild(limited);
      }
      if (state.comparisonCandidateTruncated) {
        const limited = document.createElement('div');
        limited.className = 'project-web-surface-limited';
        limited.setAttribute('role', 'status');
        limited.textContent = `Change comparisons use the newest ${state.comparisonCandidateLimit} of ${state.candidateTotal} captures. Older baselines may show as outside the comparison window.`;
        container.appendChild(limited);
      }
      if (state.loaded && !state.total) {
        container.appendChild(ctx.emptyProjectPanel(filtersActive(state)
          ? 'No captures match the current Web Surface filters.'
          : 'No HTTPx screenshots are linked to this project yet. Run a screenshot-enabled HTTP assessment to build the gallery.'));
        return;
      }
      const topPager = renderPagination(projectId, state, 'top');
      if (topPager) container.appendChild(topPager);
      container.appendChild(renderGallery(projectId, state));
      const bottomPager = renderPagination(projectId, state, 'bottom');
      if (bottomPager) container.appendChild(bottomPager);
    }

    function dispose() {
      closeViewer({ restoreFocus: false });
      viewerDismissible?.dispose?.();
      viewerFocusTrap?.dispose?.();
      viewerOverlay?.remove();
      viewerOverlay = null;
      viewerDismissible = null;
      viewerFocusTrap = null;
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
