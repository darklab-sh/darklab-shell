// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Shared, read-only rendering for bounded structured Nmap service facts.

function evidenceLabel(value) {
  return String(value || '')
    .split('_')
    .filter(Boolean)
    .map(part => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(' ');
}

function fieldPath(field) {
  const path = Array.isArray(field?.path) ? field.path : [];
  return path.map(evidenceLabel).filter(Boolean).join(' › ') || 'Value';
}

function renderNmapServiceEvidence(page, options = {}) {
  const observations = Array.isArray(page?.observations) ? page.observations : [];
  if (!observations.length) return null;
  const documentRef = options.documentRef || document;
  const section = documentRef.createElement('section');
  section.className = ['nmap-service-evidence', options.className || ''].filter(Boolean).join(' ');

  const heading = documentRef.createElement('div');
  heading.className = 'nmap-service-evidence-heading';
  const title = documentRef.createElement('strong');
  title.textContent = options.title || 'Nmap service evidence';
  const classification = documentRef.createElement('span');
  classification.className = 'badge badge-tone-muted';
  classification.textContent = 'Informational';
  heading.append(title, classification);
  section.appendChild(heading);

  const list = documentRef.createElement('div');
  list.className = 'nmap-service-evidence-list';
  observations.forEach((observation) => {
    const item = documentRef.createElement('article');
    item.className = 'nmap-service-evidence-item';
    const itemHeading = documentRef.createElement('div');
    itemHeading.className = 'nmap-service-evidence-item-heading';
    const target = documentRef.createElement('strong');
    target.textContent = String(observation?.target || 'Saved service');
    const kind = documentRef.createElement('span');
    kind.className = 'badge badge-tone-muted';
    kind.textContent = evidenceLabel(observation?.evidence_kind) || 'Service fact';
    itemHeading.append(target, kind);

    const meta = documentRef.createElement('small');
    meta.className = 'nmap-service-evidence-meta';
    meta.textContent = [
      observation?.service,
      observation?.script_id,
      observation?.tool_version ? `Nmap ${observation.tool_version}` : '',
    ].filter(Boolean).map(String).join(' · ');
    item.append(itemHeading, meta);

    const fields = Array.isArray(observation?.fields) ? observation.fields : [];
    if (fields.length) {
      const fieldList = documentRef.createElement('dl');
      fieldList.className = 'nmap-service-evidence-fields';
      fields.forEach((field) => {
        const row = documentRef.createElement('div');
        const term = documentRef.createElement('dt');
        term.textContent = fieldPath(field);
        const value = documentRef.createElement('dd');
        value.textContent = String(field?.value ?? '');
        row.append(term, value);
        fieldList.appendChild(row);
      });
      item.appendChild(fieldList);
    }

    const provenance = [
      observation?.observed_at
        ? `Observed ${typeof options.formatDate === 'function'
          ? options.formatDate(observation.observed_at)
          : observation.observed_at}`
        : '',
      observation?.parser_version ? `Parser ${observation.parser_version}` : '',
    ].filter(Boolean).join(' · ');
    if (provenance) {
      const note = documentRef.createElement('small');
      note.className = 'nmap-service-evidence-meta';
      note.textContent = provenance;
      item.appendChild(note);
    }
    list.appendChild(item);
  });
  section.appendChild(list);

  const total = Math.max(observations.length, Number(page?.total || 0));
  const truncated = observations.some(item => item?.fields_truncated || item?.collection_truncated);
  if (total > observations.length || truncated) {
    const note = documentRef.createElement('p');
    note.className = 'nmap-service-evidence-note';
    const messages = [];
    if (total > observations.length) {
      messages.push(`Showing the newest ${observations.length} of ${total} saved observations.`);
    }
    if (truncated) messages.push('Collection safety limits omitted additional structured fields.');
    note.textContent = messages.join(' ');
    section.appendChild(note);
  }
  return section;
}

export { renderNmapServiceEvidence };
