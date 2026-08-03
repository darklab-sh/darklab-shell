// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { formatPortEntityMetadata as importedFormatPortEntityMetadata } from './atlas_entity_row.js';
import { verificationStatusLabel as importedVerificationStatusLabel } from '../findings/finding_triage_bridge.js';
import { setAtlasDetailHandlers as importedSetAtlasDetailHandlers } from './atlas_bridge.js';

// Session Entity Atlas detail rendering helpers.

const _darklabGlobal = window;
const QUICK_DETAIL_PREVIEW_LIMIT = 3;

  function text(value, fallback = '') {
    return String(value ?? '').trim() || fallback;
  }

  function formatCount(value, noun) {
    const count = Number(value || 0);
    return `${count.toLocaleString()} ${noun}${count === 1 ? '' : 's'}`;
  }

  function formatDate(value) {
    const raw = text(value);
    if (!raw) return '—';
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return raw;
    return date.toLocaleString();
  }

  function clear(parent) {
    if (parent) parent.replaceChildren();
  }

  function node(tag, className = '', content = '') {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (content !== '') el.textContent = String(content);
    return el;
  }

  function metaRow(label, value) {
    const row = node('div', 'atlas-detail-meta-row');
    row.append(node('span', 'atlas-detail-meta-label', label), node('span', 'atlas-detail-meta-value', value || '—'));
    return row;
  }

  function portMetaRows(entity) {
    const formatPortEntityMetadata = typeof importedFormatPortEntityMetadata === 'function'
      ? importedFormatPortEntityMetadata
      : () => [];
    return formatPortEntityMetadata(entity, { includeHost: true })
      .map((item) => {
        const [label, ...rest] = String(item || '').split(' ');
        const value = rest.join(' ');
        return metaRow(label ? `${label.charAt(0).toUpperCase()}${label.slice(1)}` : 'Port', value);
      });
  }

  function renderLabels(labels) {
    const wrap = node('div', 'atlas-label-list');
    const values = (Array.isArray(labels) ? labels : [])
      .map(label => text(label && typeof label === 'object' ? label.label : label))
      .filter(Boolean);
    if (!values.length) {
      wrap.appendChild(node('span', 'atlas-muted', 'No labels'));
      return wrap;
    }
    values.forEach(value => wrap.appendChild(node('span', 'badge badge-tone-green', value)));
    return wrap;
  }

  function renderProjectLinks(links, onOpen, onRemove) {
    const wrap = node('div', 'atlas-project-links');
    const rows = Array.isArray(links) ? links : [];
    if (!rows.length) {
      wrap.appendChild(node('div', 'atlas-muted', 'No project links'));
      return wrap;
    }
    rows.forEach(link => {
      const row = node('div', 'atlas-project-link-row');
      const name = node('span', 'atlas-project-link-name', text(link.project_name, link.project_id || 'project'));
      const actions = node('div', 'atlas-project-link-actions');
      if (typeof onOpen === 'function') {
        const open = document.createElement('button');
        open.type = 'button';
        open.className = 'btn btn-secondary btn-compact';
        open.textContent = 'Open Project';
        open.addEventListener('click', () => onOpen(link));
        actions.appendChild(open);
      }
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'btn btn-ghost btn-compact';
      remove.textContent = 'Remove';
      remove.addEventListener('click', () => onRemove?.(link));
      actions.appendChild(remove);
      row.append(name, actions);
      wrap.appendChild(row);
    });
    return wrap;
  }

  function providerPayload(snapshot) {
    const data = snapshot?.data && typeof snapshot.data === 'object' ? snapshot.data : null;
    const providers = data?.providers && typeof data.providers === 'object' ? data.providers : null;
    if (!providers) return data;
    const label = text(snapshot.provider).toLowerCase();
    const normalizedLabel = label.replace(/[\s-]+/g, '_');
    const entries = Object.entries(providers);
    const match = entries.find(([key]) => {
      const normalizedKey = text(key).toLowerCase().replace(/[\s-]+/g, '_');
      return normalizedKey === label || normalizedKey === normalizedLabel;
    });
    if (match) return match[1];
    if (entries.length === 1) return entries[0][1];
    return providers;
  }

  function formatIntelKey(key) {
    const normalized = text(key)
      .replace(/_/g, ' ')
      .replace(/([a-z])([A-Z])/g, '$1 $2')
      .trim();
    const upper = normalized.toUpperCase();
    if (['ASN', 'AS', 'CVE', 'CVES', 'DNS', 'HTTP', 'IP', 'ISP', 'RPKI', 'TLS', 'URL'].includes(upper)) return upper;
    return normalized || 'value';
  }

  function isRecord(value) {
    return value && typeof value === 'object' && !Array.isArray(value);
  }

  function primitiveValue(value) {
    if (value === null || value === undefined || value === '') return '—';
    if (typeof value === 'boolean') return value ? 'yes' : 'no';
    if (typeof value === 'number') return value.toLocaleString();
    return String(value);
  }

  function compactJson(value) {
    try {
      const raw = JSON.stringify(value);
      if (!raw) return '—';
      return raw.length > 220 ? `${raw.slice(0, 217)}...` : raw;
    } catch (_err) {
      return primitiveValue(value);
    }
  }

  function renderIntelDataValue(value, depth = 0) {
    if (Array.isArray(value)) {
      if (!value.length) return node('span', 'atlas-intel-data-value', '—');
      const primitives = value.every(item => !isRecord(item) && !Array.isArray(item));
      if (primitives) {
        const shown = value.slice(0, 8).map(primitiveValue).join(', ');
        const suffix = value.length > 8 ? `, +${value.length - 8} more` : '';
        return node('span', 'atlas-intel-data-value', `${shown}${suffix}`);
      }
      const list = node('div', 'atlas-intel-data-list');
      value.slice(0, 4).forEach((item, index) => {
        const itemWrap = node('div', 'atlas-intel-data-item');
        itemWrap.append(
          node('div', 'atlas-intel-data-item-title', `Item ${index + 1}`),
          depth >= 2 ? node('span', 'atlas-intel-data-value', compactJson(item)) : renderIntelDataValue(item, depth + 1),
        );
        list.appendChild(itemWrap);
      });
      if (value.length > 4) list.appendChild(node('div', 'atlas-muted', `+${value.length - 4} more items`));
      return list;
    }
    if (isRecord(value)) {
      const entries = Object.entries(value)
        .filter(([, entryValue]) => entryValue !== undefined && entryValue !== null && entryValue !== '');
      if (!entries.length) return node('span', 'atlas-intel-data-value', '—');
      if (depth >= 3) return node('span', 'atlas-intel-data-value', compactJson(value));
      const wrap = node('div', `atlas-intel-data-object${depth ? ' is-nested' : ''}`);
      entries.slice(0, 12).forEach(([key, entryValue]) => {
        wrap.appendChild(renderIntelDataRow(key, entryValue, depth + 1));
      });
      if (entries.length > 12) wrap.appendChild(node('div', 'atlas-muted', `+${entries.length - 12} more fields`));
      return wrap;
    }
    return node('span', 'atlas-intel-data-value', primitiveValue(value));
  }

  function renderIntelDataRow(label, value, depth = 0) {
    const row = node('div', `atlas-intel-data-row${depth ? ' is-nested' : ''}`);
    row.append(
      node('span', 'atlas-intel-data-label', formatIntelKey(label)),
      renderIntelDataValue(value, depth),
    );
    return row;
  }

  function renderIntelPayload(snapshot) {
    const payload = providerPayload(snapshot);
    const wrap = node('div', 'atlas-intel-data');
    if (!isRecord(payload) && !Array.isArray(payload)) {
      wrap.appendChild(node('div', 'atlas-empty-inline', 'No structured provider data stored for this snapshot'));
      return wrap;
    }
    wrap.appendChild(renderIntelDataValue(payload));
    return wrap;
  }

  function renderIntelSnapshots(snapshots, options = {}) {
    const wrap = node('div', 'atlas-intel-list');
    const rows = Array.isArray(snapshots) ? snapshots : [];
    if (!rows.length) {
      const portEntity = text(options.entityType).toLowerCase() === 'port';
      wrap.appendChild(node(
        'div',
        'atlas-empty-inline',
        portEntity
          ? 'No cached provider data for port entities. Open the parent host to review provider data.'
          : 'No cached provider data. Use Refresh intel to check configured providers.',
      ));
      if (portEntity && options.parentHost && typeof options.onOpenEntity === 'function') {
        const openHost = document.createElement('button');
        openHost.type = 'button';
        openHost.className = 'btn btn-secondary btn-compact atlas-open-intel-parent';
        openHost.textContent = 'Open parent host';
        openHost.addEventListener('click', () => options.onOpenEntity(options.parentHost));
        wrap.appendChild(openHost);
      }
      return wrap;
    }
    rows.forEach(snapshot => {
      const card = node('div', 'atlas-intel-card');
      const body = node('div', 'atlas-intel-card-body u-hidden');
      let payloadRendered = false;
      const renderPayloadOnce = () => {
        if (payloadRendered) return;
        body.appendChild(renderIntelPayload(snapshot));
        payloadRendered = true;
      };
      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'btn btn-ghost btn-compact atlas-intel-card-toggle';
      toggle.setAttribute('aria-expanded', 'false');
      toggle.append(
        node('span', 'atlas-intel-card-caret', '›'),
        node('span', 'atlas-intel-provider', text(snapshot.provider, 'provider')),
        node('span', 'badge badge-tone-muted', text(snapshot.status, 'unknown')),
      );
      const summary = node('div', 'atlas-intel-summary', text(snapshot.summary, 'No summary'));
      const meta = node('div', 'atlas-muted', `Fetched ${formatDate(snapshot.fetched_at)}`);
      const disclosure = _darklabGlobal.bindDisclosure?.(toggle, {
        panel: body,
        openClass: null,
        hiddenClass: 'u-hidden',
        onToggle: (open) => {
          if (open) renderPayloadOnce();
          card.classList.toggle('is-open', open);
        },
      });
      if (!disclosure) {
        toggle.addEventListener('click', () => {
          const expanded = toggle.getAttribute('aria-expanded') === 'true';
          if (!expanded) renderPayloadOnce();
          toggle.setAttribute('aria-expanded', expanded ? 'false' : 'true');
          body.classList.toggle('u-hidden', expanded);
          card.classList.toggle('is-open', !expanded);
        });
      }
      card.append(toggle, summary, meta, body);
      wrap.appendChild(card);
    });
    return wrap;
  }

  function renderIntelSummary(summary, entityType, handlers = {}) {
    const highlights = Array.isArray(summary?.highlights) ? summary.highlights : [];
    const status = text(summary?.status, 'none');
    const freshness = text(summary?.freshness, 'not_available');
    const certificate = isRecord(summary?.certificate) ? summary.certificate : {};
    const certificateStatus = text(certificate.status, 'unknown');
    const divergence = isRecord(summary?.port_provenance?.divergence)
      ? summary.port_provenance.divergence
      : {};
    const providerPorts = Array.isArray(summary?.provider_ports) ? summary.provider_ports : [];
    const showCertificate = String(entityType || '') === 'domain' && certificateStatus !== 'unknown';
    const showPortComparison = ['domain', 'ip'].includes(String(entityType || ''))
      && (providerPorts.length || divergence.has_drift);
    if (!highlights.length && status === 'none' && !showCertificate && !showPortComparison) return null;
    const wrap = node('div', 'atlas-intel-highlights');
    const freshnessLabels = {
      fresh: 'Fresh',
      stale: 'Stale',
      unknown: 'Unknown',
      not_available: 'Not available',
    };
    const metaParts = [
      `Freshness: ${freshnessLabels[freshness] || freshness}`,
      formatCount(summary?.provider_count ?? summary?.providers_with_data?.length, 'provider'),
    ];
    if (text(summary?.last_refresh_at || summary?.updated_at)) {
      metaParts.push(`refreshed ${formatDate(summary.last_refresh_at || summary.updated_at)}`);
    }
    wrap.appendChild(node('div', 'atlas-muted atlas-intel-profile-meta', metaParts.join(' · ')));
    if (showCertificate || showPortComparison) {
      const evidence = node('div', 'atlas-detail-meta atlas-intel-profile-evidence');
      if (showCertificate) {
        const certificateLabels = {
          expired: 'Expired',
          expiring_14d: 'Expires within 14 days',
          expiring_30d: 'Expires within 30 days',
          healthy: 'Healthy',
        };
        evidence.appendChild(metaRow('Certificate', certificateLabels[certificateStatus] || certificateStatus));
        if (text(certificate.expires_at)) {
          evidence.appendChild(metaRow('Certificate expiry', formatDate(certificate.expires_at)));
        }
      }
      if (showPortComparison) {
        const appOnly = Array.isArray(divergence.app_only) ? divergence.app_only : [];
        const providerOnly = Array.isArray(divergence.provider_only) ? divergence.provider_only : [];
        const differences = [];
        if (appOnly.length) differences.push(`App only: ${appOnly.join(', ')}`);
        if (providerOnly.length) differences.push(`Provider only: ${providerOnly.join(', ')}`);
        evidence.appendChild(metaRow(
          'Recorded port comparison',
          differences.join(' · ') || 'No differences in recorded ports',
        ));
      }
      wrap.appendChild(evidence);
      if (divergence.has_drift) {
        const actions = node('div', 'atlas-intel-profile-actions');
        [
          ['View app evidence', handlers.onOpenEvidence],
          ['View provider data', handlers.onOpenIntel],
        ].forEach(([label, handler]) => {
          if (typeof handler !== 'function') return;
          const action = document.createElement('button');
          action.type = 'button';
          action.className = 'btn btn-ghost btn-compact';
          action.textContent = label;
          action.addEventListener('click', handler);
          actions.appendChild(action);
        });
        if (actions.childElementCount) wrap.appendChild(actions);
      }
    }
    const groups = new Map();
    highlights.forEach(item => {
      const providerId = text(item.provider, 'provider');
      if (!groups.has(providerId)) {
        groups.set(providerId, {
          label: text(item.provider_label, providerId),
          items: [],
        });
      }
      groups.get(providerId).items.push(item);
    });
    groups.forEach(group => {
      const providerBlock = node('div', 'atlas-intel-highlight-provider');
      providerBlock.appendChild(node('div', 'atlas-intel-highlight-provider-title', group.label));
      const itemList = node('div', 'atlas-intel-highlight-items');
      group.items.forEach(item => {
        const row = node('div', 'atlas-intel-highlight-row');
        row.append(
          node('span', 'atlas-intel-highlight-label', text(item.label, 'Intel')),
          node(
            'span',
            `atlas-intel-highlight-value${item.tone === 'warning' ? ' is-warning' : ''}`,
            text(item.value, '—'),
          ),
        );
        itemList.appendChild(row);
      });
      providerBlock.appendChild(itemList);
      wrap.appendChild(providerBlock);
    });
    return wrap;
  }

  function renderAppEvidence(evidence) {
    if (!evidence || evidence.applicable === false) return null;
    const stateLabels = {
      app_ports_found: 'App-captured ports found',
      scanned_no_ports_seen: 'Scanned, no ports surfaced',
      not_scanned: 'No app port scan recorded',
    };
    const wrap = node('div', 'atlas-detail-meta');
    wrap.append(
      metaRow('Status', stateLabels[text(evidence.coverage_state)] || 'No app port scan recorded'),
      metaRow('Scan runs', Number(evidence.scan_run_count || 0).toLocaleString()),
      metaRow('App ports', Number(evidence.app_port_count || 0).toLocaleString()),
    );
    if (text(evidence.last_observed_at)) {
      wrap.appendChild(metaRow('Last scanned', formatDate(evidence.last_observed_at)));
    }
    const roots = Array.isArray(evidence.command_roots)
      ? evidence.command_roots.map(root => text(root)).filter(Boolean)
      : [];
    if (roots.length) wrap.appendChild(metaRow('Scanners', roots.join(', ')));
    if (text(evidence.scope_note)) {
      wrap.appendChild(node('div', 'atlas-muted', text(evidence.scope_note)));
    }
    if (text(evidence.coverage_caveat)) {
      wrap.appendChild(node('div', 'atlas-muted', text(evidence.coverage_caveat)));
    }
    if (text(evidence.coverage_state) === 'not_scanned') {
      wrap.appendChild(node(
        'div',
        'atlas-empty-inline',
        'Run a port scan for this host to add app-captured port and service evidence.',
      ));
    }
    return wrap;
  }

  function renderProjectMonitoring(context) {
    if (!context || context.applicable !== true) return null;
    const state = text(context.state, 'not_monitored');
    const stateLabels = {
      not_monitored: 'Not monitored',
      active: 'Active',
      changed: 'Changed',
      failed: 'Failed',
      quiet: 'Quiet',
      paused: 'Paused',
      unavailable: 'Unavailable',
    };
    const wrap = node('div', 'atlas-project-monitoring');
    const meta = node('div', 'atlas-detail-meta');
    meta.append(
      metaRow('Status', stateLabels[state] || state),
      metaRow('Watchers', Number(context.watcher_count || 0).toLocaleString()),
    );
    if (text(context.project_name)) meta.appendChild(metaRow('Project', text(context.project_name)));
    if (text(context.latest_change_at)) {
      meta.appendChild(metaRow('Last change', formatDate(context.latest_change_at)));
    }
    wrap.appendChild(meta);

    const changes = Array.isArray(context.recent_changes) ? context.recent_changes : [];
    if (changes.length) {
      const list = node('div', 'atlas-source-list atlas-project-monitoring-changes');
      changes.forEach((change) => {
        const row = node('div', 'panel-row atlas-source-row atlas-project-monitoring-change');
        row.append(
          node('div', 'atlas-source-command', text(change.label, 'Watcher change')),
          node(
            'div',
            'atlas-muted',
            [
              text(change.watcher_label),
              text(change.severity),
              text(change.created) ? formatDate(change.created) : '',
            ].filter(Boolean).join(' · '),
          ),
        );
        list.appendChild(row);
      });
      wrap.appendChild(list);
    } else {
      wrap.appendChild(node('div', 'atlas-muted', 'No recent watcher changes for this entity'));
    }
    return wrap;
  }

  function appendCollectionAction(wrap, label, onOpen) {
    if (!wrap || typeof onOpen !== 'function' || !text(label)) return;
    const action = document.createElement('button');
    action.type = 'button';
    action.className = 'btn btn-ghost btn-compact atlas-collection-open';
    action.textContent = text(label);
    action.addEventListener('click', () => onOpen());
    wrap.appendChild(action);
  }

  function collectionTotal(meta, rows) {
    return Math.max(
      Array.isArray(rows) ? rows.length : 0,
      Number(meta?.total || 0),
    );
  }

  function renderAppPorts(observed, entityType, options = {}) {
    if (String(entityType || '') === 'port') return null;
    const allPorts = Array.isArray(observed?.app_ports) ? observed.app_ports : [];
    if (!allPorts.length) return null;
    const previewLimit = Math.max(0, Number(options.previewLimit || 0));
    const ports = previewLimit ? allPorts.slice(0, previewLimit) : allPorts;
    const wrap = node('div', 'atlas-source-list atlas-app-port-list');
    ports.forEach((port) => {
      const row = node('div', 'panel-row atlas-source-row atlas-app-port-row');
      const service = text(port.service);
      const version = text(port.version);
      const serviceLabel = service ? ` · ${service}${version ? ` (${version})` : ''}` : '';
      const title = node(
        'div',
        'atlas-source-command',
        `${Number(port.port || 0).toLocaleString()}/${text(port.proto, 'tcp')}${serviceLabel}`,
      );
      const details = [
        formatCount(port.occurrence_count, 'observation'),
        formatCount(port.source_run_count, 'source run'),
      ];
      if (text(port.last_seen_at)) details.push(`last seen ${formatDate(port.last_seen_at)}`);
      row.append(title, node('div', 'atlas-muted', details.join(' · ')));
      if (text(port.banner)) row.appendChild(node('div', 'atlas-muted', text(port.banner)));
      wrap.appendChild(row);
    });
    const total = Math.max(allPorts.length, Number(observed?.app_port_count || 0));
    if (previewLimit && total > ports.length && typeof options.onViewAll === 'function') {
      appendCollectionAction(
        wrap,
        `Open port evidence (${formatCount(total, 'port')})`,
        options.onViewAll,
      );
    } else if (observed?.app_ports_truncated && total > ports.length) {
      wrap.appendChild(node('div', 'atlas-muted', `+${(total - ports.length).toLocaleString()} more app-captured ports`));
    }
    return wrap;
  }

  function renderCollectionPager(meta, noun, onPage) {
    if (!meta) return null;
    const limit = Math.max(1, Number(meta.limit || meta.shown || 50));
    const offset = Math.max(0, Number(meta.offset || 0));
    const shown = Math.max(0, Number(meta.shown || 0));
    const total = Math.max(0, Number(meta.total || 0));
    const hasPager = total > limit || offset > 0 || !!meta.has_more;
    if (!hasPager) return null;
    const wrap = node('div', 'atlas-detail-pager');
    const start = total && shown ? offset + 1 : 0;
    const end = total ? Math.min(offset + shown, total) : offset + shown;
    wrap.appendChild(node(
      'span',
      'atlas-muted',
      total ? `${start.toLocaleString()}-${end.toLocaleString()} of ${total.toLocaleString()} ${noun}` : `Showing ${shown.toLocaleString()} ${noun}`,
    ));
    if (typeof onPage === 'function') {
      const prev = document.createElement('button');
      prev.type = 'button';
      prev.className = 'btn btn-ghost btn-compact';
      prev.textContent = 'Previous';
      prev.disabled = offset <= 0;
      prev.addEventListener('click', () => onPage(Math.max(0, offset - limit)));
      const next = document.createElement('button');
      next.type = 'button';
      next.className = 'btn btn-ghost btn-compact';
      next.textContent = 'Next';
      next.disabled = !meta.has_more;
      next.addEventListener('click', () => onPage(offset + limit));
      wrap.append(prev, next);
    }
    return wrap;
  }

  function renderRuns(runs, onSeeRun, meta = null, onPage = null, onCleanRunAtlas = null, options = {}) {
    const wrap = node('div', 'atlas-source-list');
    const allRows = Array.isArray(runs) ? runs : [];
    const previewLimit = Math.max(0, Number(options.previewLimit || 0));
    const rows = previewLimit ? allRows.slice(0, previewLimit) : allRows;
    if (!rows.length) {
      wrap.appendChild(node('div', 'atlas-empty-inline', 'No linked runs'));
      return wrap;
    }
    rows.forEach(run => {
      const row = node('div', 'panel-row atlas-source-row');
      const title = node(
        typeof onSeeRun === 'function' ? 'button' : 'div',
        `atlas-source-command${typeof onSeeRun === 'function' ? ' atlas-source-run-open' : ''}`,
        text(run.command, run.run_id),
      );
      if (title.tagName === 'BUTTON') {
        title.type = 'button';
        title.setAttribute('aria-label', `Open source run: ${text(run.command, run.run_id)}`);
        title.addEventListener('click', () => onSeeRun(run));
      }
      const meta = node(
        'div',
        'atlas-muted',
        `${formatCount(run.occurrence_count, 'hit')} · ${formatDate(run.last_seen_at || run.started)}`,
      );
      row.append(title, meta);
      if (options.showCleanup !== false && typeof onCleanRunAtlas === 'function') {
        const menu = detailActionMenu([{
          label: 'Clean from Atlas',
          onSelect: () => onCleanRunAtlas(run),
        }]);
        if (menu) row.appendChild(menu);
      }
      wrap.appendChild(row);
    });
    if (previewLimit) {
      const total = collectionTotal(meta, allRows);
      if (total > rows.length) {
        appendCollectionAction(wrap, `View all ${formatCount(total, 'source run')}`, options.onViewAll);
      }
    } else {
      const pager = renderCollectionPager(meta, 'source runs', onPage);
      if (pager) wrap.appendChild(pager);
    }
    return wrap;
  }

  function importSourceTitle(source) {
    return text(source.import_name, text(source.source_tool, 'Import'));
  }

  function importSourceLabel(source) {
    const tool = text(source.source_tool, text(source.format_id, 'external tool'));
    return source.created_record ? `Created by ${tool} import` : `Also seen in ${tool} import`;
  }

  function renderImportSources(sources, options = {}) {
    const wrap = node('div', 'atlas-source-list atlas-import-source-list');
    const allRows = Array.isArray(sources) ? sources : [];
    const previewLimit = Math.max(0, Number(options.previewLimit || 0));
    const rows = previewLimit ? allRows.slice(0, previewLimit) : allRows;
    if (!rows.length) {
      wrap.appendChild(node('div', 'atlas-empty-inline', 'No import sources'));
      return wrap;
    }
    rows.forEach(source => {
      const row = node('div', 'panel-row atlas-source-row atlas-import-source-row');
      row.append(
        node('div', 'atlas-source-command', importSourceTitle(source)),
        node(
          'div',
          'atlas-muted',
          [
            importSourceLabel(source),
            formatCount(source.occurrence_count, 'row'),
            formatDate(source.last_observed_at || source.applied_at),
          ].filter(Boolean).join(' · '),
        ),
      );
      wrap.appendChild(row);
    });
    if (previewLimit && allRows.length > rows.length) {
      appendCollectionAction(
        wrap,
        `View all ${formatCount(allRows.length, 'import source')}`,
        options.onViewAll,
      );
    }
    return wrap;
  }

  function verificationStatusLabel(value) {
    const normalized = text(value, 'not_started');
    if (typeof importedVerificationStatusLabel === 'function') {
      return importedVerificationStatusLabel(normalized);
    }
    if (_darklabGlobal.DarklabFindingTriageEditor && typeof _darklabGlobal.DarklabFindingTriageEditor.verificationStatusLabel === 'function') {
      return _darklabGlobal.DarklabFindingTriageEditor.verificationStatusLabel(normalized);
    }
    return normalized.replace(/_/g, ' ');
  }

  function renderTriageSummary(finding) {
    const triage = finding && finding.triage && typeof finding.triage === 'object' ? finding.triage : null;
    const wrap = node('div', 'atlas-triage-summary');
    if (!triage) {
      wrap.appendChild(node('div', 'atlas-muted', 'No remediation or verification details yet.'));
      return wrap;
    }
    wrap.appendChild(metaRow('Verification', verificationStatusLabel(triage.verification_status || finding.verification_status)));
    const remediation = text(triage.remediation_preview || triage.remediation);
    const steps = text(triage.verification_steps_preview || triage.verification_steps);
    if (remediation) wrap.appendChild(metaRow('Remediation', remediation));
    if (steps) wrap.appendChild(metaRow('Steps', steps));
    if (!remediation && !steps && !triage.has_verification_notes) {
      wrap.appendChild(node('div', 'atlas-muted', 'No remediation or verification text yet.'));
    }
    return wrap;
  }

  function renderFindings(
    findings,
    meta = null,
    onPage = null,
    onOpenFinding = null,
    emptyLabel = '',
    options = {},
  ) {
    const wrap = node('div', 'atlas-finding-list');
    const allRows = Array.isArray(findings) ? findings : [];
    const previewLimit = Math.max(0, Number(options.previewLimit || 0));
    const rows = previewLimit ? allRows.slice(0, previewLimit) : allRows;
    if (!rows.length) {
      wrap.appendChild(node('div', 'atlas-empty-inline', text(emptyLabel, 'No findings in this scope')));
      return wrap;
    }
    rows.forEach(finding => {
      const row = node(
        typeof onOpenFinding === 'function' ? 'button' : 'div',
        `panel-row${typeof onOpenFinding === 'function' ? ' panel-row-clickable' : ''} selection-row atlas-finding-row`,
      );
      if (row.tagName === 'BUTTON') row.type = 'button';
      const title = node('div', 'atlas-finding-title', text(finding.title || finding.raw_line, finding.id));
      const meta = node(
        'div',
        'atlas-muted',
        [text(finding.status), text(finding.severity), text(finding.tool_root)].filter(Boolean).join(' · '),
      );
      row.append(title, meta);
      if (typeof onOpenFinding === 'function') row.addEventListener('click', () => onOpenFinding(finding));
      wrap.appendChild(row);
    });
    if (previewLimit) {
      const total = collectionTotal(meta, allRows);
      if (total > rows.length) {
        appendCollectionAction(
          wrap,
          text(options.viewAllLabel, `View all ${formatCount(total, 'finding')}`),
          options.onViewAll,
        );
      }
    } else {
      const pager = renderCollectionPager(meta, 'findings', onPage);
      if (pager) wrap.appendChild(pager);
    }
    return wrap;
  }

  function renderRelatedEntities(entities, meta = null, options = {}) {
    const noun = text(options.noun, 'entities');
    const emptyLabel = text(options.emptyLabel, `No ${noun}`);
    const wrap = node('div', `atlas-source-list atlas-related-${text(options.type, 'entity')}-list`);
    const allRows = Array.isArray(entities) ? entities : [];
    const previewLimit = Math.max(0, Number(options.previewLimit || 0));
    const rows = previewLimit ? allRows.slice(0, previewLimit) : allRows;
    if (!rows.length) {
      wrap.appendChild(node('div', 'atlas-empty-inline', emptyLabel));
    } else {
      rows.forEach(relatedEntity => {
        const actionable = typeof options.onOpenEntity === 'function';
        const row = node(
          actionable ? 'button' : 'div',
          `panel-row${actionable ? ' panel-row-clickable selection-row' : ''} atlas-source-row atlas-related-${text(options.type, 'entity')}-row${actionable ? ` atlas-related-${text(options.type, 'entity')}-open` : ''}`,
        );
        if (row.tagName === 'BUTTON') row.type = 'button';
        const title = node('div', 'atlas-source-command', text(relatedEntity.canonical_value, relatedEntity.id));
        if (typeof options.onOpenEntity === 'function') {
          row.addEventListener('click', () => options.onOpenEntity(relatedEntity));
        }
        const detail = node(
          'div',
          'atlas-muted',
          `${formatCount(relatedEntity.occurrence_count, 'hit')} · ${formatDate(relatedEntity.last_seen_at)}`,
        );
        row.append(title, detail);
        wrap.appendChild(row);
      });
    }
    if (previewLimit) {
      const total = collectionTotal(meta, allRows);
      if (total > rows.length) {
        appendCollectionAction(
          wrap,
          text(options.viewAllLabel, `View all ${total.toLocaleString()} ${noun}`),
          options.onViewAll,
        );
      }
    } else {
      const pager = renderCollectionPager(meta, noun, options.onPage);
      if (pager) wrap.appendChild(pager);
    }
    return wrap;
  }

  function findingSummaryDetail(rollup) {
    const total = Math.max(0, Number(rollup?.total || 0));
    const severity = rollup?.by_severity || {};
    const attention = Number(severity.critical || 0) + Number(severity.high || 0);
    const parts = [];
    if (attention) parts.push(`${attention.toLocaleString()} critical/high`);
    if (Number(rollup?.suppressed || 0)) parts.push(`${Number(rollup.suppressed).toLocaleString()} suppressed`);
    if (parts.length) return parts.join(' · ');
    if (!total) return 'No findings in this scope';
    const review = rollup?.by_review_state || {};
    const reviewLabels = [
      ['new', 'new'],
      ['needs_followup', 'follow-up'],
      ['important', 'important'],
      ['reviewed', 'reviewed'],
      ['false_positive', 'false positive'],
    ];
    const reviewSummary = reviewLabels
      .map(([key, label]) => [Number(review[key] || 0), label])
      .filter(([count]) => count > 0)
      .slice(0, 2)
      .map(([count, label]) => `${count.toLocaleString()} ${label}`);
    return reviewSummary.join(' · ') || `${formatCount(total, 'active finding')}`;
  }

  function findingSummaryCard(label, rollup, bucket, onOpen, primary = false) {
    const actionable = typeof onOpen === 'function' && rollup?.applicable !== false;
    const card = node(
      actionable ? 'button' : 'div',
      `atlas-finding-summary-card${actionable ? ' btn btn-ghost' : ''}${primary ? ' is-primary' : ''}`,
    );
    if (actionable) {
      card.type = 'button';
      card.dataset.atlasFindingBucket = bucket;
      card.setAttribute('aria-label', `${label}: ${formatCount(rollup?.total, 'finding')}`);
      card.addEventListener('click', () => onOpen(bucket));
    }
    card.append(
      node('strong', '', Number(rollup?.total || 0).toLocaleString()),
      node('span', '', label),
      node('div', 'atlas-muted', findingSummaryDetail(rollup)),
    );
    return card;
  }

  function renderFindingSummary(summary, entityType, onOpen) {
    if (!summary || typeof summary !== 'object') return null;
    const wrap = node('div', 'atlas-finding-summary-grid');
    wrap.appendChild(findingSummaryCard('On this entity', summary.direct, 'direct', onOpen, true));
    if (['domain', 'ip'].includes(String(entityType || ''))) {
      wrap.append(
        findingSummaryCard('On related URLs', summary.related_urls, 'related_urls', onOpen),
        findingSummaryCard('On related ports', summary.related_ports, 'related_ports', onOpen),
        findingSummaryCard('Across this host surface', summary.combined, 'combined', onOpen),
      );
    }
    return wrap;
  }

  function renderParentHost(parentHost, onOpenEntity) {
    return renderRelatedEntities(parentHost ? [parentHost] : [], null, {
      type: 'host',
      noun: 'parent host',
      emptyLabel: 'No parent host recorded',
      onOpenEntity,
    });
  }

  function reviewStateSelect(value, onChange, options = {}) {
    const select = document.createElement('select');
    select.className = 'form-select form-control-compact atlas-finding-review';
    select.setAttribute('aria-label', 'Finding review state');
    [
      ['new', 'New'],
      ['reviewed', 'Reviewed'],
      ['important', 'Important'],
      ['false_positive', 'False positive'],
      ['needs_followup', 'Follow-up'],
    ].forEach(([optionValue, label]) => {
      const option = document.createElement('option');
      option.value = optionValue;
      option.textContent = label;
      select.appendChild(option);
    });
    select.value = text(value, 'new');
    select.disabled = !!options.disabled;
    if (options.disabledReason) select.title = options.disabledReason;
    select.addEventListener('change', () => onChange?.(select.value));
    return select;
  }

  function detailActionMenu(items = []) {
    const activeItems = items.filter(item => item && item.label && typeof item.onSelect === 'function');
    if (!activeItems.length) return null;
    const wrap = node('div', 'atlas-detail-action-menu save-menu-wrap save-menu-down');
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'btn btn-secondary btn-compact atlas-detail-action-menu-trigger';
    trigger.textContent = 'Actions';
    trigger.setAttribute('aria-haspopup', 'menu');
    trigger.setAttribute('aria-expanded', 'false');
    const menu = node('div', 'atlas-detail-action-menu-list save-menu dropdown-surface');
    menu.setAttribute('role', 'menu');
    let outsideClickHandler = null;
    let escapeHandler = null;
    const closeMenu = () => {
      wrap.classList.remove('open');
      trigger.setAttribute('aria-expanded', 'false');
      menu.removeAttribute('style');
      if (outsideClickHandler) {
        document.removeEventListener('click', outsideClickHandler);
        outsideClickHandler = null;
      }
      if (escapeHandler) {
        document.removeEventListener('keydown', escapeHandler);
        escapeHandler = null;
      }
    };
    const bindCloseHandlers = () => {
      if (outsideClickHandler || typeof document === 'undefined') return;
      outsideClickHandler = (event) => {
        const target = event.target;
        if (target && typeof target.closest === 'function') {
          if (target.closest('.atlas-detail-action-menu') || target.closest('.atlas-detail-action-menu-list')) return;
        }
        closeMenu();
      };
      escapeHandler = (event) => {
        if (event.key === 'Escape') closeMenu();
      };
      document.addEventListener('click', outsideClickHandler);
      document.addEventListener('keydown', escapeHandler);
    };
    activeItems.forEach(item => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `dropdown-item dropdown-item-compact${item.destructive ? ' is-destructive' : ''}`;
      button.setAttribute('role', 'menuitem');
      button.textContent = item.label;
      button.disabled = !!item.disabled;
      if (item.disabled) {
        button.setAttribute('aria-disabled', 'true');
        if (item.disabledReason) button.title = item.disabledReason;
      }
      button.addEventListener('click', () => {
        if (item.disabled) return;
        closeMenu();
        item.onSelect();
      });
      menu.appendChild(button);
    });
    const positionMenu = () => {
      const rect = trigger.getBoundingClientRect();
      const menuWidth = Math.max(160, menu.offsetWidth || 160);
      const margin = 8;
      const left = Math.min(
        Math.max(margin, rect.left),
        Math.max(margin, window.innerWidth - menuWidth - margin),
      );
      const top = Math.max(margin, rect.bottom - 1);
      menu.style.left = `${left}px`;
      menu.style.top = `${top}px`;
      menu.style.right = 'auto';
      menu.style.bottom = 'auto';
    };
    trigger.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      const open = !wrap.classList.contains('open');
      wrap.classList.toggle('open', open);
      trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (open) {
        positionMenu();
        bindCloseHandlers();
      } else {
        closeMenu();
      }
    });
    wrap.append(trigger, menu);
    return wrap;
  }

  function renderFindingDetail(container, finding, handlers = {}) {
    clear(container);
    if (!container) return;
    if (!finding || !finding.id) {
      container.appendChild(node('div', 'atlas-empty-inline', 'Select a finding'));
      return;
    }
    if (typeof handlers.onBack === 'function' && !handlers.hideBackAction) {
      const back = document.createElement('button');
      back.type = 'button';
      back.className = 'btn btn-ghost btn-compact atlas-detail-back';
      back.textContent = '← Back to entity';
      back.addEventListener('click', () => handlers.onBack(finding));
      container.appendChild(back);
    }
    const header = node('div', 'atlas-detail-identity');
    header.append(
      node('div', 'atlas-detail-type', text(finding.kind, 'FINDING').toUpperCase()),
      node('div', 'atlas-detail-value', text(finding.title || finding.raw_line, finding.id)),
    );
    const meta = node('div', 'atlas-detail-meta');
    meta.append(
      metaRow('Status', text(finding.review_state || finding.status, 'new')),
      metaRow('Suppression', finding.suppressed ? text(finding.suppressed_reason, 'suppressed') : 'visible'),
      metaRow('Severity', text(finding.severity, '—')),
      metaRow('Tool', text(finding.tool_root, '—')),
      metaRow('Entity', text(finding.entity_value, finding.subject_key || '—')),
      metaRow('Occurrences', Number(finding.occurrence_count || 0).toLocaleString()),
      metaRow('Last seen', formatDate(finding.last_seen_at)),
    );
    const raw = node('code', 'atlas-finding-raw', text(finding.raw_line, finding.title || finding.id));
    container.append(header);
    if (!handlers.hideInlineActions) {
      const actions = node('div', 'atlas-detail-actions');
      actions.appendChild(reviewStateSelect(
        finding.review_state || finding.status,
        (reviewState) => handlers.onReviewState?.(finding, reviewState),
        {
          disabled: handlers.canTriageAtlasRows === false,
          disabledReason: handlers.triageDisabledReason || '',
        },
      ));
      const triage = document.createElement('button');
      triage.type = 'button';
      triage.className = 'btn btn-secondary btn-compact';
      triage.textContent = 'Triage';
      triage.addEventListener('click', () => handlers.onEditTriage?.(finding));
      actions.appendChild(triage);
      if (finding.run_id) {
        const run = document.createElement('button');
        run.type = 'button';
        run.className = 'btn btn-secondary btn-compact';
        run.textContent = 'See in run';
        run.addEventListener('click', () => handlers.onSeeRun?.(finding));
        actions.appendChild(run);
      }
      const menuItems = [];
      if (finding.entity_id) {
        menuItems.push({
          label: 'Open entity',
          onSelect: () => handlers.onOpenEntity?.(finding),
        });
      }
      menuItems.push(
        {
          label: finding.suppressed ? 'Restore finding' : 'Suppress finding',
          disabled: handlers.canTriageAtlasRows === false,
          disabledReason: handlers.triageDisabledReason || '',
          onSelect: () => handlers.onSuppressFinding?.(finding),
        },
        {
          label: 'Delete finding',
          destructive: true,
          disabled: handlers.canDeleteAtlasRows === false,
          disabledReason: handlers.deleteDisabledReason || '',
          onSelect: () => handlers.onDeleteFinding?.(finding),
        },
      );
      const menu = detailActionMenu(menuItems);
      if (menu) actions.appendChild(menu);
      container.append(actions);
      if (typeof _darklabGlobal.enhanceAppSelects === 'function') {
        _darklabGlobal.enhanceAppSelects(actions);
      }
    }
    container.append(meta);
    container.append(section('Remediation and verification', renderTriageSummary(finding)));
    container.append(section('Import sources', renderImportSources(finding.import_sources)));
    container.append(section('Evidence', raw));
  }

  function renderMetadataEditor(entity, handlers = {}) {
    const wrap = node('div', 'atlas-metadata-editor');
    const labelInput = document.createElement('input');
    labelInput.className = 'form-control form-control-compact';
    labelInput.type = 'text';
    labelInput.autocomplete = 'off';
    labelInput.placeholder = 'labels';
    labelInput.setAttribute('aria-label', 'Atlas entity labels');
    labelInput.value = (Array.isArray(entity.labels) ? entity.labels : [])
      .map(label => text(label && typeof label === 'object' ? label.label : label))
      .filter(Boolean)
      .join(', ');

    const noteInput = document.createElement('textarea');
    noteInput.className = 'form-control atlas-note-input nice-scroll';
    noteInput.rows = 3;
    noteInput.placeholder = 'note';
    noteInput.setAttribute('aria-label', 'Atlas entity note');
    noteInput.value = text(entity.note && entity.note.body);

    const save = document.createElement('button');
    save.type = 'button';
    save.className = 'btn btn-secondary btn-compact';
    save.textContent = 'Save metadata';
    save.addEventListener('click', () => handlers.onSaveMetadata?.({
      labels: labelInput.value,
      note: noteInput.value,
    }));

    wrap.append(labelInput, noteInput, save);
    return wrap;
  }

  const profileViews = [
    ['overview', 'Overview'],
    ['evidence', 'Evidence'],
    ['findings', 'Findings'],
    ['intel', 'Intel'],
  ];

  function normalizedProfileView(value) {
    const requested = text(value, 'overview').toLowerCase();
    return profileViews.some(([view]) => view === requested) ? requested : 'overview';
  }

  function renderProfileNavigation(activeView, onChange) {
    const active = normalizedProfileView(activeView);
    const wrap = node('div', 'atlas-profile-tabs tab-strip');
    wrap.setAttribute('role', 'tablist');
    wrap.setAttribute('aria-label', 'Entity profile views');
    profileViews.forEach(([view, label], index) => {
      const button = document.createElement('button');
      const selected = view === active;
      button.type = 'button';
      button.className = `tab-strip-item atlas-profile-tab${selected ? ' is-active active' : ''}`;
      button.dataset.atlasProfileView = view;
      button.setAttribute('role', 'tab');
      button.setAttribute('aria-selected', selected ? 'true' : 'false');
      button.setAttribute('aria-pressed', selected ? 'true' : 'false');
      button.textContent = label;
      button.addEventListener('click', () => onChange?.(view, { focus: true }));
      button.addEventListener('keydown', (event) => {
        const keys = ['ArrowLeft', 'ArrowRight', 'Home', 'End'];
        if (!keys.includes(event.key)) return;
        event.preventDefault();
        let nextIndex = index;
        if (event.key === 'ArrowLeft') nextIndex = (index - 1 + profileViews.length) % profileViews.length;
        if (event.key === 'ArrowRight') nextIndex = (index + 1) % profileViews.length;
        if (event.key === 'Home') nextIndex = 0;
        if (event.key === 'End') nextIndex = profileViews.length - 1;
        onChange?.(profileViews[nextIndex][0], { focus: true });
      });
      wrap.appendChild(button);
    });
    return wrap;
  }

  function renderProfileSections(detail, entity, handlers, parts) {
    const activeView = normalizedProfileView(handlers.profileView);
    if (activeView === 'evidence') {
      return sectionGroup('Evidence', [
        parts.appEvidence ? section('Scan coverage', parts.appEvidence) : null,
        parts.appPorts ? section(
          String(entity.type || '') === 'url'
            ? 'App-captured ports (parent host)'
            : 'App-captured ports',
          parts.appPorts,
        ) : null,
        section('Source runs', renderRuns(
          detail.runs,
          handlers.onSeeRun,
          detail.detail_limits?.runs,
          handlers.onPageRuns,
          handlers.onCleanRunAtlas,
        )),
        section('Import sources', renderImportSources(detail.import_sources)),
      ]);
    }
    if (activeView === 'findings') {
      const findingBucket = text(detail.detail_limits?.findings?.bucket, 'direct');
      const findingLabels = {
        direct: ['Direct findings', 'No direct findings on this entity'],
        related_urls: ['Findings on related URLs', 'No findings on related URLs'],
        related_ports: ['Findings on related ports', 'No findings on related ports'],
        combined: ['Findings across this host surface', 'No findings across this host surface'],
      };
      const [findingTitle, findingEmpty] = findingLabels[findingBucket] || findingLabels.direct;
      return sectionGroup('Findings', [
        parts.findingSummary ? section('Summary', parts.findingSummary) : null,
        section(findingTitle, renderFindings(
          detail.findings,
          detail.detail_limits?.findings,
          handlers.onPageFindings,
          handlers.onOpenFinding,
          findingEmpty,
        )),
      ]);
    }
    if (activeView === 'intel') {
      return sectionGroup('External intelligence', [
        parts.intelSummary ? section('Summary', parts.intelSummary) : null,
        section('Cached provider data', renderIntelSnapshots(detail.intel_snapshots, {
          entityType: entity.type,
          parentHost: detail.parent_host,
          onOpenEntity: handlers.onOpenEntity,
        })),
      ]);
    }
    return [
      sectionGroup('Overview', [
        section('Summary', parts.meta),
        parts.findingSummary ? section('Findings and work', parts.findingSummary) : null,
        parts.projectMonitoring ? section('Project monitoring', parts.projectMonitoring) : null,
      ]),
      sectionGroup('Relationships', parts.relationshipSections),
      sectionGroup('Metadata', parts.metadataSections),
    ];
  }

  function renderDetail(container, detail, handlers = {}) {
    clear(container);
    if (!container) return;
    if (!detail || !detail.entity) {
      container.appendChild(node('div', 'atlas-empty-inline', 'Select an entity'));
      return;
    }
    const entity = detail.entity;
    const header = node('div', 'atlas-detail-identity');
    header.append(
      node('div', 'atlas-detail-type', text(entity.type).toUpperCase()),
      node('div', 'atlas-detail-value', text(entity.canonical_value, entity.id)),
    );

    const meta = node('div', 'atlas-detail-meta');
    meta.append(
      metaRow('Suppression', entity.suppressed ? text(entity.suppressed_reason, 'suppressed') : 'visible'),
      ...portMetaRows(entity),
      metaRow('Occurrences', Number(entity.occurrence_count || 0).toLocaleString()),
      metaRow('First seen', formatDate(entity.first_seen_at)),
      metaRow('Last seen', formatDate(entity.last_seen_at)),
    );

    if (handlers.profileMode && typeof handlers.onExitProfile === 'function' && !handlers.hideProfileBackAction) {
      const back = document.createElement('button');
      back.type = 'button';
      back.className = 'btn btn-ghost btn-compact atlas-profile-back';
      back.textContent = `\u2190 ${text(handlers.profileBackLabel, 'Back to results')}`;
      back.addEventListener('click', () => handlers.onExitProfile());
      container.appendChild(back);
    }
    container.append(header);
    if (!handlers.hideInlineActions) {
      const actions = node('div', 'atlas-detail-actions');
      if (String(entity.type || '') !== 'port') {
        const refresh = document.createElement('button');
        refresh.type = 'button';
        refresh.className = 'btn btn-secondary btn-compact';
        refresh.disabled = !!handlers.intelRefreshing;
        refresh.setAttribute('aria-busy', handlers.intelRefreshing ? 'true' : 'false');
        refresh.textContent = handlers.intelRefreshing ? 'Refreshing...' : 'Refresh intel';
        refresh.addEventListener('click', () => handlers.onRefreshIntel?.(entity));
        actions.appendChild(refresh);
      }
      if (handlers.activeProject && !handlers.isLinkedToActiveProject?.(entity)) {
        const promote = document.createElement('button');
        promote.type = 'button';
        promote.className = 'btn btn-secondary btn-compact';
        promote.textContent = 'Add to active project';
        promote.addEventListener('click', () => handlers.onAddToActiveProject?.(entity));
        actions.appendChild(promote);
      }
      if (!handlers.profileMode && typeof handlers.onViewProfile === 'function') {
        const profile = document.createElement('button');
        profile.type = 'button';
        profile.className = 'btn btn-primary btn-compact atlas-view-profile';
        profile.textContent = 'View profile';
        profile.addEventListener('click', () => handlers.onViewProfile?.('overview'));
        actions.appendChild(profile);
      }
      const menu = detailActionMenu([
        {
          label: entity.suppressed ? 'Restore entity' : 'Suppress entity',
          disabled: handlers.canTriageAtlasRows === false,
          disabledReason: handlers.triageDisabledReason || '',
          onSelect: () => handlers.onSuppressEntity?.(entity),
        },
        {
          label: 'Delete entity',
          destructive: true,
          disabled: handlers.canDeleteAtlasRows === false,
          disabledReason: handlers.deleteDisabledReason || '',
          onSelect: () => handlers.onDeleteEntity?.(entity),
        },
      ]);
      if (menu) actions.appendChild(menu);
      container.append(actions);
    }
    const quickDetail = !handlers.profileMode;
    const appEvidence = renderAppEvidence(detail.overview?.observed?.app_evidence);
    const appPorts = renderAppPorts(detail.overview?.observed, entity.type, quickDetail ? {
      previewLimit: QUICK_DETAIL_PREVIEW_LIMIT,
      onViewAll: handlers.onOpenEvidence,
    } : {});
    const projectMonitoring = renderProjectMonitoring(detail.overview?.observed?.project_monitoring);
    const observedSections = [
      section('Summary', meta),
      appEvidence ? section('Scan coverage', appEvidence) : null,
      projectMonitoring ? section('Project monitoring', projectMonitoring) : null,
    ];
    const findingSummary = renderFindingSummary(
      detail.finding_summary,
      entity.type,
      handlers.onOpenFindingBucket,
    );
    const findingSections = [];
    if (findingSummary) findingSections.push(section('Summary', findingSummary));
    findingSections.push(section('Direct findings', renderFindings(
      detail.findings,
      detail.detail_limits?.findings,
      handlers.onPageFindings,
      handlers.onOpenFinding,
      'No direct findings on this entity',
      quickDetail ? {
        previewLimit: QUICK_DETAIL_PREVIEW_LIMIT,
        onViewAll: () => handlers.onOpenFindingBucket?.('direct'),
      } : {},
    )));
    const relationshipSections = [];
    if (detail.parent_host) {
      relationshipSections.push(section('Parent host', renderParentHost(detail.parent_host, handlers.onOpenEntity)));
    }
    relationshipSections.push(section(
      'Projects',
      renderProjectLinks(entity.project_links, handlers.onOpenProject, handlers.onRemoveProjectLink),
    ));
    if (['domain', 'ip'].includes(String(entity.type || ''))) {
      relationshipSections.push(section('Related URLs', renderRelatedEntities(
        detail.related_urls,
        detail.detail_limits?.related_urls,
        {
          type: 'url',
          noun: 'related URLs',
          onOpenEntity: handlers.onOpenEntity,
          onPage: handlers.onPageRelatedUrls,
          previewLimit: quickDetail ? QUICK_DETAIL_PREVIEW_LIMIT : 0,
          onViewAll: quickDetail ? () => handlers.onViewProfile?.('overview') : null,
        },
      )));
      relationshipSections.push(section('Related ports', renderRelatedEntities(
        detail.related_ports,
        detail.detail_limits?.related_ports,
        {
          type: 'port',
          noun: 'related ports',
          onOpenEntity: handlers.onOpenEntity,
          onPage: handlers.onPageRelatedPorts,
          previewLimit: quickDetail ? QUICK_DETAIL_PREVIEW_LIMIT : 0,
          onViewAll: quickDetail ? () => handlers.onViewProfile?.('overview') : null,
        },
      )));
    }
    const evidenceSections = [
      appPorts ? section(
        String(entity.type || '') === 'url'
          ? 'App-captured ports (parent host)'
          : 'App-captured ports',
        appPorts,
      ) : null,
      section('Source runs', renderRuns(
        detail.runs,
        handlers.onSeeRun,
        detail.detail_limits?.runs,
        handlers.onPageRuns,
        handlers.onCleanRunAtlas,
        {
          previewLimit: QUICK_DETAIL_PREVIEW_LIMIT,
          onViewAll: handlers.onOpenEvidence,
          showCleanup: false,
        },
      )),
      section('Import sources', renderImportSources(detail.import_sources, {
        previewLimit: QUICK_DETAIL_PREVIEW_LIMIT,
        onViewAll: handlers.onOpenEvidence,
      })),
    ];
    const metadataSections = [
      section('Labels', renderLabels(entity.labels)),
      section('Edit metadata', renderMetadataEditor(entity, handlers)),
    ];
    const intelSummary = renderIntelSummary(
      detail.overview?.intel || detail.intel_summary,
      entity.type,
      {
        onOpenEvidence: handlers.onOpenEvidence,
        onOpenIntel: handlers.onOpenIntel,
      },
    );
    const intelSections = [];
    if (intelSummary) intelSections.push(section('Summary', intelSummary));
    intelSections.push(section('Cached provider data', renderIntelSnapshots(detail.intel_snapshots, {
      entityType: entity.type,
      parentHost: detail.parent_host,
      onOpenEntity: handlers.onOpenEntity,
    })));
    if (handlers.profileMode) {
      container.appendChild(renderProfileNavigation(handlers.profileView, handlers.onProfileViewChange));
      const focused = renderProfileSections(detail, entity, handlers, {
        appEvidence,
        appPorts,
        projectMonitoring,
        findingSummary,
        intelSummary,
        meta,
        relationshipSections,
        metadataSections,
      });
      (Array.isArray(focused) ? focused : [focused]).filter(Boolean).forEach(item => container.appendChild(item));
      return;
    }
    container.append(
      sectionGroup('Observed by darklab_shell', observedSections),
      sectionGroup('Findings and work', findingSections),
      sectionGroup('Relationships', relationshipSections),
      sectionGroup('Evidence', evidenceSections),
      sectionGroup('Metadata', metadataSections),
      sectionGroup('External intelligence', intelSections),
    );
  }

  function sectionGroup(title, sections = []) {
    const wrap = node('section', 'atlas-detail-group');
    const heading = node('div', 'atlas-detail-group-title', title);
    heading.setAttribute('role', 'heading');
    heading.setAttribute('aria-level', '3');
    const body = node('div', 'atlas-detail-group-body');
    sections.filter(Boolean).forEach(item => body.appendChild(item));
    wrap.append(heading, body);
    return wrap;
  }

  function section(title, content) {
    const wrap = node('section', 'atlas-detail-section');
    wrap.append(node('div', 'atlas-detail-section-title', title), content);
    return wrap;
  }

  const DarklabAtlasDetail = {
    renderDetail,
    renderFindingDetail,
    reviewStateSelect,
    formatCount,
    formatDate,
    text,
    node,
  };

  if (typeof importedSetAtlasDetailHandlers === 'function') {
    importedSetAtlasDetailHandlers({ DarklabAtlasDetail });
  }

export {
  DarklabAtlasDetail,
  formatCount,
  formatDate,
  node,
  renderDetail,
  renderFindingDetail,
  reviewStateSelect,
  text,
};
