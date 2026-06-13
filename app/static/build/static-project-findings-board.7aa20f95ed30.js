// Project Findings board view controller.
// Loaded before shell_chrome.js; shell chrome supplies shared findings actions.

(function projectFindingsBoardModule(global) {
  'use strict';

  function createProjectFindingsBoardController(context) {
    const ctx = context || {};

    function cardMeta(projectId, summary, card) {
      const finding = card.finding || {};
      return [
        card.run_command || card.run_id,
        card.scope || 'finding',
        ctx.projectFindingTargetText(summary, finding) || ctx.projectTargetLabel(summary, card.target_id),
        `line ${card.line_number || 0}`,
      ].filter(Boolean).join(ctx.metaSeparator || ' - ');
    }

    function cardActions(projectId, card) {
      const finding = card.finding || {};
      const wrap = document.createElement('div');
      wrap.className = 'project-finding-board-card-actions';
      if (card.run_id) {
        const open = ctx.makeProjectButton('Open', 'open-finding', projectId);
        open.dataset.findingId = card.id;
        open.dataset.runId = card.run_id;
        open.dataset.runCommand = card.run_command;
        open.dataset.lineIndex = Number.isInteger(card.line_number) ? String(card.line_number) : '';
        wrap.appendChild(open);
      }
      if (card.id) {
        const triage = ctx.makeProjectButton('Triage', 'edit-finding-triage', projectId);
        triage.dataset.findingId = card.id;
        wrap.appendChild(triage);
        const edit = ctx.makeProjectButton('Edit', 'edit-finding-metadata', projectId);
        edit.dataset.findingId = card.id;
        wrap.appendChild(edit);
        wrap.appendChild(ctx.reviewControl(finding, projectId));
      }
      return wrap;
    }

    function boardBadge(label, tone = 'muted') {
      const el = document.createElement('span');
      const toneClass = {
        amber: 'badge-tone-amber',
        red: 'badge-tone-red',
        green: 'badge-tone-green',
      }[tone] || 'badge-tone-muted';
      el.className = `badge ${toneClass}`;
      el.textContent = String(label || '');
      return el;
    }

    function severityTone(severity) {
      const normalized = String(severity || '').toLowerCase();
      return normalized === 'high' || normalized === 'critical' ? 'red' : 'muted';
    }

    function cardFinding(card) {
      const finding = card.finding && typeof card.finding === 'object' ? card.finding : {};
      return {
        ...finding,
        triage: finding.triage || card.triage,
        verification_status: finding.verification_status || card.verification_status,
      };
    }

    function renderCard(projectId, summary, card) {
      const article = document.createElement('article');
      article.className = [
        'project-finding-board-card',
        `review-${card.review_state || 'new'}`,
        card.severity ? `severity-${card.severity}` : '',
      ].filter(Boolean).join(' ');
      article.tabIndex = 0;
      article.dataset.findingId = card.id;

      const header = document.createElement('div');
      header.className = 'project-finding-board-card-header';
      const title = document.createElement('div');
      title.className = 'project-finding-board-card-title';
      title.textContent = card.title || card.raw_line || card.id || 'Finding';
      header.appendChild(title);
      const badges = document.createElement('div');
      badges.className = 'project-finding-board-card-badges';
      if (card.important) {
        badges.appendChild(boardBadge('important', 'amber'));
      }
      if (card.severity) {
        badges.appendChild(boardBadge(card.severity, severityTone(card.severity)));
      }
      if (badges.children.length) header.appendChild(badges);
      article.appendChild(header);

      const meta = cardMeta(projectId, summary, card);
      if (meta) {
        const metaEl = document.createElement('div');
        metaEl.className = 'project-finding-board-card-meta';
        metaEl.textContent = meta;
        article.appendChild(metaEl);
      }
      if (card.raw_line && card.raw_line !== card.title) {
        const detail = document.createElement('div');
        detail.className = 'project-finding-board-card-detail';
        detail.textContent = card.raw_line;
        article.appendChild(detail);
      }
      const chips = ctx.entityMetadataChips(cardFinding(card));
      if (Array.isArray(chips) && chips.length) {
        const chipWrap = document.createElement('div');
        chipWrap.className = 'project-finding-board-card-chips';
        chips.forEach((chip) => {
          const chipEl = document.createElement('span');
          chipEl.className = ctx.entityMetadataChipClass(chip.kind);
          chipEl.textContent = String(chip.label || '');
          chipWrap.appendChild(chipEl);
        });
        article.appendChild(chipWrap);
      }
      article.appendChild(cardActions(projectId, card));
      return article;
    }

    function renderColumn(projectId, summary, column) {
      const section = document.createElement('section');
      section.className = 'project-finding-board-column';
      section.setAttribute('aria-labelledby', `project-finding-board-${column.state}`);

      const header = document.createElement('div');
      header.className = 'project-finding-board-column-header';
      const title = document.createElement('h3');
      title.id = `project-finding-board-${column.state}`;
      title.textContent = column.label;
      const count = document.createElement('span');
      count.className = 'project-finding-board-column-count';
      count.textContent = String(column.total || 0);
      header.append(title, count);
      section.appendChild(header);

      const body = document.createElement('div');
      body.className = 'project-finding-board-column-body';
      if (column.cards.length) {
        column.cards.forEach(card => body.appendChild(renderCard(projectId, summary, card)));
      } else {
        const empty = document.createElement('div');
        empty.className = 'project-finding-board-empty';
        empty.textContent = 'No findings';
        body.appendChild(empty);
      }
      if (column.truncated) {
        const truncated = document.createElement('div');
        truncated.className = 'project-finding-board-truncated';
        truncated.textContent = `Showing ${column.cards.length} of ${column.total}`;
        body.appendChild(truncated);
      }
      section.appendChild(body);
      return section;
    }

    function renderBoard(container, projectId, summary, board) {
      const wrap = document.createElement('div');
      wrap.className = 'project-finding-board';
      wrap.setAttribute('aria-label', 'Finding review board');
      (board.columns || []).forEach(column => wrap.appendChild(renderColumn(projectId, summary, column)));
      container.appendChild(wrap);
    }

    return {
      renderBoard,
    };
  }

  global.DarklabProjectFindingsBoard = {
    createProjectFindingsBoardController,
  };
})(globalThis);
