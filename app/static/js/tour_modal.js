(function (global) {
  'use strict';

  const ILLUSTRATION_KEYS = [
    'terminal_stream',
    'tab_complete',
    'history_rows',
    'compare_runs',
    'workflow_steps',
    'project_summary',
    'files_panel',
    'pty_terminal',
    'session_token',
    'next_steps',
  ];

  let _overlay = null;
  let _currentIndex = 0;
  let _returnFocusEl = null;

  function _isMobileViewport() {
    return typeof global.useMobileTerminalViewportMode === 'function'
      && global.useMobileTerminalViewportMode();
  }

  function _tourEnabled() {
    return !!(global.APP_CONFIG && global.APP_CONFIG.tour_enabled === true);
  }

  function _visibleTourModalChapters() {
    if (!_tourEnabled() || _isMobileViewport()) return [];
    const chapters = Array.isArray(global.APP_CONFIG?.tour_chapters)
      ? global.APP_CONFIG.tour_chapters
      : [];
    return chapters.filter(chapter => chapter && typeof chapter === 'object');
  }

  function _summaryLines(summary) {
    return String(summary || '')
      .split('\n')
      .map(line => line.trim())
      .filter(Boolean);
  }

  function _createMiniLine(text, cls = '') {
    const line = document.createElement('span');
    line.className = `tour-mini-line ${cls}`.trim();
    line.textContent = text;
    return line;
  }

  function _createMiniPill(text, cls = '') {
    const pill = document.createElement('span');
    pill.className = `tour-mini-pill ${cls}`.trim();
    pill.textContent = text;
    return pill;
  }

  function _renderTourIllustration(key) {
    const normalized = ILLUSTRATION_KEYS.includes(String(key || ''))
      ? String(key)
      : 'terminal_stream';
    const card = document.createElement('div');
    card.className = `tour-visual-card tour-visual-${normalized}`;
    card.setAttribute('aria-hidden', 'true');

    if (normalized === 'terminal_stream') {
      card.append(
        _createMiniLine('$ dig darklab.sh A', 'is-command'),
        _createMiniLine('darklab.sh. 300 IN A 203.0.113.10', 'is-output'),
        _createMiniLine('exit 0 · 2 lines · 0.2s', 'is-muted'),
      );
      return card;
    }

    if (normalized === 'tab_complete') {
      const row = document.createElement('div');
      row.className = 'tour-mini-input-row';
      row.append(_createMiniPill('nmap', 'is-root'), _createMiniPill('-sV'), _createMiniPill('darklab.sh'));
      const menu = document.createElement('div');
      menu.className = 'tour-mini-menu';
      menu.append(_createMiniLine('--top-ports'), _createMiniLine('--script'), _createMiniLine('-oN'));
      card.append(row, menu);
      return card;
    }

    if (normalized === 'history_rows') {
      ['nmap darklab.sh', 'curl -I https://darklab.sh', 'dig darklab.sh A'].forEach((cmd, index) => {
        const row = document.createElement('div');
        row.className = 'tour-mini-row';
        row.append(_createMiniLine(cmd, 'is-command'), _createMiniPill(index === 0 ? 'starred' : 'restore'));
        card.appendChild(row);
      });
      return card;
    }

    if (normalized === 'compare_runs') {
      const split = document.createElement('div');
      split.className = 'tour-mini-split';
      const left = document.createElement('div');
      left.append(_createMiniLine('80/tcp open http'), _createMiniLine('443/tcp open https'));
      const right = document.createElement('div');
      right.append(_createMiniLine('443/tcp open https'), _createMiniLine('8443/tcp open https', 'is-added'));
      split.append(left, right);
      card.append(split, _createMiniLine('2 changed · findings matched out of order', 'is-muted'));
      return card;
    }

    if (normalized === 'workflow_steps') {
      ['DNS', 'TLS', 'HTTP'].forEach((step, index) => {
        const row = document.createElement('div');
        row.className = 'tour-mini-row';
        row.append(_createMiniPill(String(index + 1)), _createMiniLine(step, 'is-command'), _createMiniPill('Run'));
        card.appendChild(row);
      });
      return card;
    }

    if (normalized === 'project_summary') {
      const header = document.createElement('div');
      header.className = 'tour-mini-row';
      header.append(_createMiniLine('darklab.sh', 'is-command'), _createMiniPill('active', 'is-green'));
      const chips = document.createElement('div');
      chips.className = 'tour-mini-chip-row';
      chips.append(_createMiniPill('runs 9'), _createMiniPill('findings 137'), _createMiniPill('targets 10'));
      card.append(header, chips);
      return card;
    }

    if (normalized === 'files_panel') {
      ['targets.txt', 'reports/nmap.txt', 'captures/headers.txt'].forEach(name => {
        card.appendChild(_createMiniLine(name, 'is-output'));
      });
      card.appendChild(_createMiniLine('edit · preview · download', 'is-muted'));
      return card;
    }

    if (normalized === 'pty_terminal') {
      card.append(
        _createMiniLine('$ mtr --interactive darklab.sh', 'is-command'),
        _createMiniLine('Keys stream to the tool in real time', 'is-output'),
        _createMiniLine('transcript saved to history', 'is-muted'),
      );
      return card;
    }

    if (normalized === 'session_token') {
      card.append(
        _createMiniLine('tok_a0b2********', 'is-command'),
        _createMiniLine('history · projects · files · options', 'is-output'),
        _createMiniLine('moves with you', 'is-muted'),
      );
      return card;
    }

    card.append(
      _createMiniLine('help', 'is-command'),
      _createMiniLine('commands info <tool>', 'is-command'),
      _createMiniLine('FAQ · themes · options', 'is-output'),
    );
    return card;
  }

  function _loadSampleCommand(sample) {
    const command = String(sample || '').trim();
    if (!command) return;
    if (typeof global.refocusComposerAfterAction === 'function') {
      global.refocusComposerAfterAction();
    }
    if (typeof global.setComposerValue === 'function') {
      global.setComposerValue(command, command.length, command.length, { dispatch: false });
    } else if (global.cmdInput) {
      global.cmdInput.value = command;
    }
    const input = global.cmdInput || document.getElementById('cmd');
    if (input && typeof input.dispatchEvent === 'function') {
      setTimeout(() => input.dispatchEvent(new Event('input')), 0);
    }
  }

  function _bindPressable(el, onActivate) {
    if (!el) return;
    if (typeof global.bindPressable === 'function') {
      global.bindPressable(el, {
        refocusComposer: false,
        clearPressStyle: true,
        onActivate,
      });
    } else {
      el.addEventListener('click', onActivate);
    }
  }

  function _ensureTourModal() {
    if (_overlay) return _overlay;
    const overlay = document.createElement('div');
    overlay.id = 'tour-overlay';
    overlay.className = 'modal-overlay tour-overlay u-hidden';
    overlay.setAttribute('aria-hidden', 'true');
    overlay.innerHTML = `
      <section id="tour-modal" class="modal-card tour-modal" role="dialog" aria-modal="true" aria-labelledby="tour-title" tabindex="-1">
        <div class="tour-modal-header">
          <div>
            <div id="tour-title" class="tour-modal-eyebrow">TOUR</div>
            <div id="tour-chapter-title" class="tour-modal-title"></div>
          </div>
          <button type="button" class="close-btn tour-close" aria-label="Close tour">✕</button>
        </div>
        <div class="tour-modal-body">
          <div id="tour-visual" class="tour-modal-visual"></div>
          <div class="tour-modal-copy">
            <div id="tour-chapter-summary" class="tour-modal-summary"></div>
            <div id="tour-sample-host" class="tour-sample-host"></div>
          </div>
        </div>
        <div class="tour-modal-footer">
          <div id="tour-step-list" class="tour-step-list" aria-label="Tour progress"></div>
          <div class="tour-modal-actions">
            <button type="button" id="tour-prev-btn" class="btn btn-secondary btn-compact">Prev</button>
            <button type="button" id="tour-next-btn" class="btn btn-primary btn-compact">Next</button>
          </div>
        </div>
      </section>
    `;
    document.body.appendChild(overlay);
    const modal = overlay.querySelector('#tour-modal');
    const closeBtn = overlay.querySelector('.tour-close');
    const prevBtn = overlay.querySelector('#tour-prev-btn');
    const nextBtn = overlay.querySelector('#tour-next-btn');

    _bindPressable(prevBtn, () => _goTourChapter(-1));
    _bindPressable(nextBtn, () => _goTourChapter(1));

    if (typeof global.bindFocusTrap === 'function') {
      global.bindFocusTrap(modal);
    }
    if (typeof global.bindDismissible === 'function') {
      global.bindDismissible(overlay, {
        level: 'modal',
        isOpen: () => overlay.classList.contains('open'),
        onClose: closeTourModal,
        closeButtons: closeBtn,
      });
    } else {
      overlay.addEventListener('click', event => {
        if (event.target === overlay) closeTourModal();
      });
      closeBtn.addEventListener('click', closeTourModal);
    }
    _overlay = overlay;
    return overlay;
  }

  function _renderTourStepDots(chapters) {
    const host = _overlay.querySelector('#tour-step-list');
    host.innerHTML = '';
    chapters.forEach((chapter, index) => {
      const dot = document.createElement('button');
      dot.type = 'button';
      dot.className = 'tour-step-dot';
      dot.setAttribute('aria-label', `Open ${chapter.title || `chapter ${index + 1}`}`);
      dot.setAttribute('aria-current', index === _currentIndex ? 'step' : 'false');
      dot.dataset.tourStep = String(index);
      _bindPressable(dot, () => {
        _currentIndex = index;
        _renderTourChapter();
      });
      host.appendChild(dot);
    });
  }

  function _renderTourChapter() {
    const chapters = _visibleTourModalChapters();
    if (!_overlay || !chapters.length) return;
    _currentIndex = Math.max(0, Math.min(_currentIndex, chapters.length - 1));
    const chapter = chapters[_currentIndex];
    const title = _overlay.querySelector('#tour-chapter-title');
    const summary = _overlay.querySelector('#tour-chapter-summary');
    const visual = _overlay.querySelector('#tour-visual');
    const sampleHost = _overlay.querySelector('#tour-sample-host');
    const prevBtn = _overlay.querySelector('#tour-prev-btn');
    const nextBtn = _overlay.querySelector('#tour-next-btn');

    title.textContent = chapter.title || 'Tour';
    summary.innerHTML = '';
    _summaryLines(chapter.summary).forEach(line => {
      const p = document.createElement('p');
      p.textContent = line;
      summary.appendChild(p);
    });
    visual.innerHTML = '';
    visual.appendChild(_renderTourIllustration(chapter.illustration));

    sampleHost.innerHTML = '';
    const sample = String(chapter.sample || '').trim();
    if (sample) {
      const label = document.createElement('span');
      label.className = 'tour-sample-label';
      label.textContent = 'Try this';
      const chip = document.createElement('span');
      chip.className = 'tour-sample-chip welcome-command-loadable';
      chip.tabIndex = 0;
      chip.setAttribute('role', 'button');
      chip.setAttribute('aria-label', `Load command: ${sample}`);
      chip.textContent = sample;
      _bindPressable(chip, () => _loadSampleCommand(sample));
      sampleHost.append(label, chip);
    }

    prevBtn.disabled = _currentIndex === 0;
    nextBtn.disabled = _currentIndex === chapters.length - 1;
    nextBtn.textContent = _currentIndex === chapters.length - 1 ? 'Done' : 'Next';
    if (_currentIndex === chapters.length - 1) {
      nextBtn.disabled = false;
      nextBtn.onclick = null;
    }
    _renderTourStepDots(chapters);
  }

  function _goTourChapter(delta) {
    const chapters = _visibleTourModalChapters();
    if (!chapters.length) return;
    if (_currentIndex === chapters.length - 1 && delta > 0) {
      closeTourModal();
      return;
    }
    _currentIndex = Math.max(0, Math.min(_currentIndex + delta, chapters.length - 1));
    _renderTourChapter();
  }

  function _focusTourModal() {
    const modal = _overlay && _overlay.querySelector('#tour-modal');
    if (!modal || typeof modal.focus !== 'function') return;
    try {
      modal.focus({ preventScroll: true });
    } catch (_) {
      modal.focus();
    }
  }

  async function _recordTourModalOpened() {
    if (typeof global._recordTourOpenedOnceThisSession === 'function') {
      await global._recordTourOpenedOnceThisSession();
    } else if (typeof global.recordTourOpened === 'function') {
      try { await global.recordTourOpened(); } catch (_) { /* best-effort */ }
    }
  }

  function openTourModal(options = {}) {
    const chapters = _visibleTourModalChapters();
    if (!chapters.length) return false;
    const overlay = _ensureTourModal();
    const requestedId = String(options.chapterId || '');
    const requestedIndex = chapters.findIndex(chapter => String(chapter.id || '') === requestedId);
    _currentIndex = requestedIndex >= 0 ? requestedIndex : 0;
    _returnFocusEl = options.returnFocus && typeof options.returnFocus.focus === 'function'
      ? options.returnFocus
      : null;
    _renderTourChapter();
    overlay.classList.remove('u-hidden');
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
    _recordTourModalOpened();
    const schedule = typeof requestAnimationFrame === 'function'
      ? requestAnimationFrame
      : (callback) => setTimeout(callback, 0);
    schedule(_focusTourModal);
    return true;
  }

  function closeTourModal() {
    if (!_overlay) return;
    _overlay.classList.remove('open');
    _overlay.classList.add('u-hidden');
    _overlay.setAttribute('aria-hidden', 'true');
    if (_returnFocusEl && _returnFocusEl.isConnected && typeof _returnFocusEl.focus === 'function') {
      try {
        _returnFocusEl.focus({ preventScroll: true });
      } catch (_) {
        _returnFocusEl.focus();
      }
      _returnFocusEl = null;
      return;
    }
    _returnFocusEl = null;
    if (typeof global.refocusComposerAfterAction === 'function') {
      global.refocusComposerAfterAction({ preventScroll: true });
    }
  }

  global.openTourModal = openTourModal;
  global.closeTourModal = closeTourModal;
  global._visibleTourModalChapters = _visibleTourModalChapters;
  global._renderTourIllustration = _renderTourIllustration;
})(typeof window !== 'undefined' ? window : globalThis);
