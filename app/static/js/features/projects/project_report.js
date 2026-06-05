// Project engagement report controller.
// Loaded before shell_chrome.js; shell chrome supplies Projects state and shared UI helpers.

(function initProjectReport(global) {
  if (typeof document === 'undefined') return;

  function createProjectReportController(context) {
    const ctx = context || {};
    const stateByProject = new Map();
    const reportJobPollMs = 750;
    const dateRangeHelp = 'Expected format: YYYY-MM-DD to YYYY-MM-DD, for example 2026-06-01 to 2026-06-05.';
    const metadataFields = [
      ['engagement_name', 'Engagement name', 'input'],
      ['date_range', 'Date range', 'input', { placeholder: '2026-06-01 to 2026-06-05', title: dateRangeHelp }],
      ['operator', 'Operator', 'input'],
      ['client', 'Client', 'input'],
      ['contact', 'Contact', 'input'],
      ['executive_summary', 'Executive summary', 'textarea'],
      ['methodology', 'Methodology', 'textarea'],
      ['cover_notes', 'Cover notes', 'textarea'],
    ];
    const selectionKinds = [
      ['run_ids', 'Runs', 'run', (item) => item.command || item.id, (item) => ctx.formatDate?.(item.started) || item.id],
      ['target_ids', 'Targets', 'target', (item) => item.value || item.canonical_value || item.id, (item) => item.type || 'target'],
      ['finding_ids', 'Findings', 'finding', (item) => item.title || item.raw_line || item.id, (item) => item.severity || item.review_state || 'finding'],
      ['artifact_ids', 'Artifacts', 'artifact', (item) => item.display_name || item.workspace_path || item.id, (item) => ctx.projectArtifactDetail?.(item) || item.kind || 'artifact'],
    ];

    function canMutateProjects() {
      return typeof global.activeTeamScopeCan === 'function'
        ? global.activeTeamScopeCan('mutate_projects')
        : true;
    }

    function deniedMessage() {
      return typeof global.teamScopeDeniedMessage === 'function'
        ? global.teamScopeDeniedMessage('change team projects')
        : "View-only team members can't change team projects. Switch to Personal or ask for operator access.";
    }

    function defaultDraft() {
      return {
        metadata: Object.fromEntries(metadataFields.map(([key]) => [key, ''])),
        sections: [
          ['cover', 'Cover'],
          ['executive_summary', 'Executive summary'],
          ['scope_targets', 'Scope and targets'],
          ['methodology', 'Methodology'],
          ['findings_by_severity', 'Findings by severity'],
          ['included_runs', 'Included runs'],
          ['artifacts', 'Artifacts'],
          ['appendix', 'Appendix'],
        ].map(([type, title]) => ({ type, title, enabled: true })),
        selection: {
          run_ids: [],
          artifact_ids: [],
          entity_ids: [],
          finding_ids: [],
          target_ids: [],
        },
        selection_modes: {
          run_ids: 'all',
          artifact_ids: 'all',
          entity_ids: 'all',
          finding_ids: 'all',
          target_ids: 'all',
        },
        export: {
          redaction_mode: 'redacted',
          include_private_notes: false,
        },
      };
    }

    function clone(value) {
      try {
        return JSON.parse(JSON.stringify(value || {}));
      } catch (_) {
        return {};
      }
    }

    function normalizeDraft(draft) {
      const base = defaultDraft();
      const raw = draft && typeof draft === 'object' ? draft : {};
      const metadata = raw.metadata && typeof raw.metadata === 'object' ? raw.metadata : {};
      const selection = raw.selection && typeof raw.selection === 'object' ? raw.selection : {};
      const selectionModes = raw.selection_modes && typeof raw.selection_modes === 'object' ? raw.selection_modes : {};
      const exportPrefs = raw.export && typeof raw.export === 'object' ? raw.export : {};
      const rawSections = Array.isArray(raw.sections) ? raw.sections : base.sections;
      const known = new Map(base.sections.map(section => [section.type, section]));
      const sections = [];
      const seen = new Set();
      rawSections.forEach((section) => {
        if (!section || typeof section !== 'object') return;
        const type = String(section.type || '').trim();
        if (!known.has(type) || seen.has(type)) return;
        seen.add(type);
        sections.push({
          type,
          title: String(section.title || known.get(type).title || type),
          enabled: section.enabled !== false,
        });
      });
      base.sections.forEach((section) => {
        if (!seen.has(section.type)) sections.push({ ...section });
      });
      return {
        metadata: {
          ...base.metadata,
          ...Object.fromEntries(metadataFields.map(([key]) => [key, String(metadata[key] || '')])),
        },
        sections,
        selection: {
          ...base.selection,
          ...Object.fromEntries(Object.keys(base.selection).map((key) => [
            key,
            Array.isArray(selection[key])
              ? selection[key].map(value => String(value || '')).filter(Boolean)
              : [],
          ])),
        },
        selection_modes: {
          ...base.selection_modes,
          ...Object.fromEntries(Object.keys(base.selection_modes).map((key) => {
            const mode = String(selectionModes[key] || 'all').trim().toLowerCase();
            return [key, mode === 'manual' ? 'manual' : 'all'];
          })),
        },
        export: {
          redaction_mode: String(exportPrefs.redaction_mode || 'redacted') === 'raw' ? 'raw' : 'redacted',
          include_private_notes: !!exportPrefs.include_private_notes,
        },
      };
    }

    function stateFor(projectId) {
      const normalized = String(projectId || '').trim();
      if (!stateByProject.has(normalized)) {
        stateByProject.set(normalized, {
          projectId: normalized,
          loading: false,
          saving: false,
          previewing: false,
          exporting: false,
          loaded: false,
          dirty: false,
          error: '',
          notice: '',
          report: null,
          updated: '',
          draft: defaultDraft(),
          preview: null,
          templates: [],
          selectionItemsLoaded: false,
          selectionItemsLoading: false,
        });
      }
      return stateByProject.get(normalized);
    }

    function readJsonResponse(resp, fallbackMessage) {
      return Promise.resolve(resp)
        .then(async (response) => {
          const data = await response.json().catch(() => ({}));
          if (!response.ok) {
            throw new Error(data.error || data.message || fallbackMessage || 'Request failed.');
          }
          return data;
        });
    }

    function projectUrl(projectId, suffix = '') {
      return `/projects/${encodeURIComponent(projectId)}/report${suffix}`;
    }

    function jsonRequestOptions(options = {}) {
      return {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...(options.headers || {}),
        },
      };
    }

    function selectedItems(summary, key) {
      if (key === 'run_ids') return ctx.projectRunItems?.(summary) || [];
      if (key === 'target_ids') return ctx.projectTargetItems?.(summary) || [];
      if (key === 'finding_ids') return ctx.projectFindingItems?.(String(summary?.project?.id || ctx.getSelectedProjectId?.() || '')) || [];
      if (key === 'artifact_ids') return ctx.projectArtifactItems?.(summary) || [];
      return [];
    }

    function selectionSet(st, key, summary) {
      const explicit = st.draft.selection && Array.isArray(st.draft.selection[key]) ? st.draft.selection[key] : [];
      const items = selectedItems(summary, key);
      if (!explicit.length && st.draft.selection_modes?.[key] !== 'manual') {
        return new Set(items.map(item => String(item && item.id || '')).filter(Boolean));
      }
      return new Set(explicit.map(value => String(value || '')).filter(Boolean));
    }

    function syncSelectionFromDom(st, root, key) {
      if (!root || !key) return;
      const inputs = Array.from(root.querySelectorAll(`[data-project-report-selection="${key}"]`));
      const checked = inputs
        .filter(input => input.checked && !input.disabled)
        .map(input => String(input.value || '').trim())
        .filter(Boolean);
      st.draft.selection[key] = checked;
      if (inputs.length && st.draft.selection_modes) st.draft.selection_modes[key] = 'manual';
    }

    function refreshPreviewPanel(st, root) {
      const host = root?.querySelector?.('.project-report-preview-wrap');
      if (!host) return;
      host.replaceChildren();
      renderPreview(st, host);
    }

    function markDirty(st, root = null) {
      const hadPreview = !!st.preview;
      st.dirty = true;
      st.notice = '';
      st.error = '';
      if (hadPreview) {
        st.preview = null;
        refreshPreviewPanel(st, root);
      }
    }

    async function load(projectId, { render = true } = {}) {
      const st = stateFor(projectId);
      if (st.loading || st.loaded) return st;
      st.loading = true;
      st.error = '';
      if (render) ctx.renderProjectExplorer?.();
      try {
        const resp = await ctx.apiFetch(projectUrl(projectId), { cache: 'no-store' });
        const data = await readJsonResponse(resp, 'Unable to load report draft.');
        st.report = data.report || null;
        st.updated = String(data.report?.updated || '');
        st.draft = normalizeDraft(data.report?.draft || {});
        st.templates = Array.isArray(data.templates) ? data.templates : [];
        st.preview = null;
        st.dirty = false;
        st.loaded = true;
      } catch (err) {
        st.error = err.message || 'Unable to load report draft.';
        ctx.logClientError?.('failed to load project report', err);
      } finally {
        st.loading = false;
        if (render) ctx.renderProjectExplorer?.();
      }
      return st;
    }

    function visibleRoot(projectId) {
      return Array.from(document.querySelectorAll('[data-project-report-root]'))
        .find(root => String(root.dataset.projectReportRoot || '') === String(projectId || '')) || null;
    }

    function syncEditableFields(st, root = visibleRoot(st.projectId)) {
      if (!root) return;
      metadataFields.forEach(([key]) => {
        const field = root.querySelector(`[data-project-report-metadata="${key}"]`);
        if (field) st.draft.metadata[key] = String(field.value || '');
      });
      root.querySelectorAll('[data-project-report-section-toggle]').forEach((input) => {
        const index = Number(input.dataset.projectReportSectionToggle || -1);
        if (Number.isInteger(index) && st.draft.sections[index]) {
          st.draft.sections[index].enabled = !!input.checked;
        }
      });
      const redaction = root.querySelector('[data-project-report-export="redaction_mode"]');
      if (redaction) st.draft.export.redaction_mode = String(redaction.value || 'redacted') === 'raw' ? 'raw' : 'redacted';
      const privateNotes = root.querySelector('[data-project-report-export="include_private_notes"]');
      if (privateNotes) st.draft.export.include_private_notes = !!privateNotes.checked;
    }

    function requestDraft(st) {
      const draft = clone(st.draft);
      if (!canMutateProjects()) {
        draft.export = {
          ...(draft.export || {}),
          redaction_mode: 'redacted',
          include_private_notes: false,
        };
      }
      return draft;
    }

    async function save(projectId, root = visibleRoot(projectId)) {
      const st = stateFor(projectId);
      if (!canMutateProjects()) {
        st.error = deniedMessage();
        ctx.renderProjectExplorer?.();
        return;
      }
      syncEditableFields(st, root);
      st.saving = true;
      st.error = '';
      ctx.renderProjectExplorer?.();
      try {
        const resp = await ctx.apiFetch(projectUrl(projectId), jsonRequestOptions({
          method: 'POST',
          body: JSON.stringify({
            draft: st.draft,
            expected_updated: st.updated || '',
          }),
        }));
        const data = await readJsonResponse(resp, 'Unable to save report draft.');
        st.report = data.report || null;
        st.updated = String(data.report?.updated || '');
        st.draft = normalizeDraft(data.report?.draft || st.draft);
        st.dirty = false;
        st.notice = 'Report draft saved.';
        ctx.setProjectWorkspaceMessage?.('Report draft saved.');
      } catch (err) {
        st.error = err.message || 'Unable to save report draft.';
        ctx.logClientError?.('failed to save project report draft', err);
      } finally {
        st.saving = false;
        ctx.renderProjectExplorer?.();
      }
    }

    async function preview(projectId, root = visibleRoot(projectId)) {
      const st = stateFor(projectId);
      syncEditableFields(st, root);
      st.previewing = true;
      st.error = '';
      ctx.renderProjectExplorer?.();
      try {
        const resp = await ctx.apiFetch(projectUrl(projectId, '/preview'), jsonRequestOptions({
          method: 'POST',
          body: JSON.stringify({ draft: requestDraft(st) }),
        }));
        const data = await readJsonResponse(resp, 'Unable to preview report.');
        st.preview = data.preview || null;
        st.notice = 'Preview updated.';
      } catch (err) {
        st.error = err.message || 'Unable to preview report.';
        ctx.logClientError?.('failed to preview project report', err);
      } finally {
        st.previewing = false;
        ctx.renderProjectExplorer?.();
      }
    }

    function waitForReportJob(projectId, job) {
      let current = job && typeof job === 'object' ? job : {};
      return new Promise((resolve, reject) => {
        const poll = async () => {
          if (String(current.status || '') === 'complete') {
            resolve(current);
            return;
          }
          if (String(current.status || '') === 'failed') {
            reject(new Error(current.error || 'Unable to export report.'));
            return;
          }
          const st = stateFor(projectId);
          st.notice = `Preparing report archive: ${current.message || current.phase || 'queued'}`;
          ctx.renderProjectExplorer?.();
          window.setTimeout(async () => {
            try {
              const resp = await ctx.apiFetch(
                `${projectUrl(projectId, '/export-jobs')}/${encodeURIComponent(current.id || '')}`,
                { cache: 'no-store' },
              );
              const data = await readJsonResponse(resp, 'Unable to check report export status.');
              current = data.job || {};
              poll();
            } catch (err) {
              reject(err);
            }
          }, reportJobPollMs);
        };
        poll();
      });
    }

    async function exportReport(projectId, root = visibleRoot(projectId)) {
      const st = stateFor(projectId);
      syncEditableFields(st, root);
      st.exporting = true;
      st.error = '';
      ctx.renderProjectExplorer?.();
      try {
        const startResp = await ctx.apiFetch(projectUrl(projectId, '/export'), jsonRequestOptions({
          method: 'POST',
          body: JSON.stringify({ draft: requestDraft(st) }),
          cache: 'no-store',
        }));
        const startData = await readJsonResponse(startResp, 'Unable to start report export.');
        const job = await waitForReportJob(projectId, startData.job || {});
        const ticketResp = await ctx.apiFetch(
          `${projectUrl(projectId, '/export-jobs')}/${encodeURIComponent(job.id || '')}/download-ticket`,
          { method: 'POST', cache: 'no-store' },
        );
        const ticketData = await readJsonResponse(ticketResp, 'Unable to download report.');
        const name = reportArchiveName(ctx.selectedProject?.(), st.draft);
        ctx.downloadUrlAsAttachment?.(ticketData.url, name, 'Report download started.');
        st.notice = 'Report download started.';
      } catch (err) {
        st.error = err.message || 'Unable to export report.';
        ctx.logClientError?.('failed to export project report', err);
      } finally {
        st.exporting = false;
        ctx.renderProjectExplorer?.();
      }
    }

    function printReport(projectId) {
      const st = stateFor(projectId);
      if (!st.preview || !st.preview.html) {
        st.error = 'Preview the report before printing or saving as PDF.';
        ctx.renderProjectExplorer?.();
        return;
      }
      const printWindow = window.open('', '_blank');
      if (!printWindow || !printWindow.document) {
        st.error = 'Unable to open the print window. Allow pop-ups and try again.';
        ctx.renderProjectExplorer?.();
        return;
      }
      printWindow.document.open();
      printWindow.document.write(String(st.preview.html || ''));
      printWindow.document.close();
      printWindow.focus?.();
      window.setTimeout(() => {
        try {
          printWindow.print?.();
        } catch (err) {
          st.error = err.message || 'Unable to start the browser print flow.';
          ctx.logClientError?.('failed to print project report', err);
          ctx.renderProjectExplorer?.();
        }
      }, 0);
    }

    async function confirmReloadSavedDraft() {
      const confirmFn = typeof ctx.showConfirm === 'function'
        ? ctx.showConfirm
        : (typeof global.showConfirm === 'function' ? global.showConfirm : null);
      if (confirmFn) {
        const choice = await confirmFn({
          body: {
            text: 'Reload the saved report draft?',
            note: 'Unsaved report edits will be discarded.',
          },
          tone: 'warning',
          actions: [
            { id: 'cancel', label: 'Cancel', role: 'cancel' },
            { id: 'reload', label: 'Reload saved', tone: 'warning' },
          ],
        });
        return choice === 'reload';
      }
      if (typeof global.confirm === 'function') {
        return global.confirm('Reload the saved report draft? Unsaved report edits will be discarded.');
      }
      return false;
    }

    function reportArchiveName(project, draft) {
      const raw = String(draft?.metadata?.engagement_name || project?.slug || project?.name || 'engagement-report')
        .trim()
        .toLowerCase();
      const safe = raw.replace(/[^a-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '') || 'engagement-report';
      return `${safe}.zip`;
    }

    function applyTemplate(st, templateId) {
      const template = st.templates.find(item => String(item.id || '') === String(templateId || ''));
      if (!template || !Array.isArray(template.sections)) return;
      st.draft.sections = normalizeDraft({ sections: template.sections }).sections;
      markDirty(st);
    }

    function moveSection(st, index, offset) {
      const sections = st.draft.sections;
      const nextIndex = index + offset;
      if (nextIndex < 0 || nextIndex >= sections.length) return;
      const [item] = sections.splice(index, 1);
      sections.splice(nextIndex, 0, item);
      markDirty(st);
    }

    function fieldLabel(key) {
      const match = metadataFields.find(([field]) => field === key);
      return match ? match[1] : key.replace(/_/g, ' ');
    }

    function ensureFullSelectionItems(projectId, summary) {
      const st = stateFor(projectId);
      if (st.selectionItemsLoaded || st.selectionItemsLoading) return st.selectionItemsLoaded;
      const tasks = [];
      if (typeof ctx.loadProjectFindings === 'function') {
        tasks.push(Promise.resolve(ctx.loadProjectFindings(projectId, {
          allPages: true,
          skipInitialRender: true,
          skipFinalRender: true,
        })));
      }
      if (typeof ctx.loadAllProjectArtifacts === 'function') {
        tasks.push(Promise.resolve(ctx.loadAllProjectArtifacts(projectId, summary)));
      }
      if (!tasks.length) {
        st.selectionItemsLoaded = true;
        return true;
      }
      st.selectionItemsLoading = true;
      Promise.all(tasks).then(() => {
        st.selectionItemsLoaded = true;
      }).catch((err) => {
        st.error = err?.message || 'Unable to load full report item lists.';
        ctx.logClientError?.('failed to load report item lists', err);
      }).finally(() => {
        st.selectionItemsLoading = false;
        ctx.renderProjectExplorer?.();
      });
      return false;
    }

    function renderNotice(st, host) {
      const message = st.error || st.notice;
      if (!message) return;
      const note = document.createElement('div');
      note.className = `project-report-message${st.error ? ' is-error' : ''}`;
      note.textContent = message;
      host.appendChild(note);
    }

    function renderMetadata(st, host) {
      const section = document.createElement('section');
      section.className = 'project-report-panel project-report-metadata';
      const heading = document.createElement('h3');
      heading.textContent = 'Metadata';
      section.appendChild(heading);
      const grid = document.createElement('div');
      grid.className = 'project-report-field-grid';
      metadataFields.forEach(([key, label, type, options]) => {
        const wrap = document.createElement('label');
        wrap.className = type === 'textarea' ? 'project-report-field project-report-field-wide' : 'project-report-field';
        wrap.textContent = label;
        const input = document.createElement(type === 'textarea' ? 'textarea' : 'input');
        input.className = 'form-control form-control-compact';
        input.dataset.projectReportMetadata = key;
        input.value = st.draft.metadata[key] || '';
        if (options?.placeholder) input.placeholder = options.placeholder;
        if (options?.title) {
          input.title = options.title;
          wrap.title = options.title;
        }
        if (type === 'textarea') input.rows = key === 'executive_summary' ? 5 : 4;
        wrap.appendChild(input);
        grid.appendChild(wrap);
      });
      section.appendChild(grid);
      host.appendChild(section);
    }

    function renderTemplates(st, host) {
      if (st.templates.length <= 1) return;
      const section = document.createElement('section');
      section.className = 'project-report-panel project-report-templates';
      const label = document.createElement('label');
      label.textContent = 'Template';
      const select = document.createElement('select');
      select.className = 'form-select';
      select.dataset.projectReportTemplate = '1';
      const placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = 'Choose a template';
      select.appendChild(placeholder);
      st.templates.forEach((template) => {
        const option = document.createElement('option');
        option.value = String(template.id || '');
        option.textContent = template.label || template.id || 'Template';
        select.appendChild(option);
      });
      label.appendChild(select);
      section.appendChild(label);
      host.appendChild(section);
    }

    function renderSections(st, host) {
      const section = document.createElement('section');
      section.className = 'project-report-panel project-report-sections';
      const heading = document.createElement('h3');
      heading.textContent = 'Sections';
      section.appendChild(heading);
      st.draft.sections.forEach((item, index) => {
        const row = document.createElement('div');
        row.className = 'project-report-section-row';
        const label = document.createElement('label');
        label.className = 'project-report-check-row';
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = item.enabled !== false;
        checkbox.dataset.projectReportSectionToggle = String(index);
        const text = document.createElement('span');
        text.textContent = item.title || item.type;
        label.append(checkbox, text);
        const controls = document.createElement('div');
        controls.className = 'project-report-section-controls';
        const up = button('↑', 'Move up', 'section-up');
        up.disabled = index === 0;
        up.dataset.sectionIndex = String(index);
        const down = button('↓', 'Move down', 'section-down');
        down.disabled = index === st.draft.sections.length - 1;
        down.dataset.sectionIndex = String(index);
        controls.append(up, down);
        row.append(label, controls);
        section.appendChild(row);
      });
      host.appendChild(section);
    }

    function button(text, title, action, role = 'secondary') {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = `btn btn-${role} btn-compact`;
      btn.textContent = text;
      btn.title = title;
      btn.dataset.projectReportAction = action;
      ctx.bindProjectRuntimePressable?.(btn);
      return btn;
    }

    function renderExportPrefs(st, host) {
      const section = document.createElement('section');
      section.className = 'project-report-panel project-report-export-prefs';
      const heading = document.createElement('h3');
      heading.textContent = 'Export';
      section.appendChild(heading);
      const redactionLabel = document.createElement('label');
      redactionLabel.textContent = 'Redaction';
      const redaction = document.createElement('select');
      redaction.className = 'form-select';
      redaction.dataset.projectReportExport = 'redaction_mode';
      const canMutate = canMutateProjects();
      const displayExport = canMutate ? st.draft.export : { redaction_mode: 'redacted', include_private_notes: false };
      redaction.disabled = !canMutate;
      [
        ['redacted', 'Redacted'],
        ['raw', 'Raw'],
      ].forEach(([value, label]) => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = label;
        option.selected = displayExport.redaction_mode === value;
        redaction.appendChild(option);
      });
      redactionLabel.appendChild(redaction);
      const privateLabel = document.createElement('label');
      privateLabel.className = 'project-report-check-row';
      const privateInput = document.createElement('input');
      privateInput.type = 'checkbox';
      privateInput.checked = !!displayExport.include_private_notes;
      privateInput.disabled = !canMutate;
      privateInput.dataset.projectReportExport = 'include_private_notes';
      const privateText = document.createElement('span');
      privateText.textContent = 'Include private notes';
      privateLabel.append(privateInput, privateText);
      section.append(redactionLabel, privateLabel);
      if (!canMutate) {
        const note = document.createElement('p');
        note.className = 'project-report-note';
        note.textContent = deniedMessage();
        section.appendChild(note);
      }
      host.appendChild(section);
    }

    function renderSelection(st, host, projectId, summary) {
      const section = document.createElement('section');
      section.className = 'project-report-panel project-report-selection';
      const heading = document.createElement('h3');
      heading.textContent = 'Included items';
      section.appendChild(heading);
      selectionKinds.forEach(([key, title, kind, labelFn, detailFn]) => {
        const items = selectedItems(summary, key);
        const selected = selectionSet(st, key, summary);
        const group = document.createElement('div');
        group.className = 'project-report-selection-group';
        const groupHeader = document.createElement('div');
        groupHeader.className = 'project-report-selection-heading';
        const groupTitle = document.createElement('h4');
        groupTitle.textContent = `${title} (${items.length})`;
        const controls = document.createElement('div');
        controls.className = 'project-report-selection-actions';
        const selectAll = button('All', `Select all ${title.toLowerCase()}`, 'selection-all');
        selectAll.dataset.selectionKey = key;
        const clear = button('None', `Clear ${title.toLowerCase()}`, 'selection-none');
        clear.dataset.selectionKey = key;
        controls.append(selectAll, clear);
        groupHeader.append(groupTitle, controls);
        group.appendChild(groupHeader);
        if (!items.length) {
          group.appendChild(ctx.emptyProjectPanel?.(`No ${title.toLowerCase()} available.`) || document.createElement('div'));
        } else {
          items.forEach((item) => {
            const id = String(item.id || '');
            const row = document.createElement('label');
            row.className = 'project-report-check-row project-report-selection-row';
            const input = document.createElement('input');
            input.type = 'checkbox';
            input.value = id;
            input.checked = selected.has(id);
            input.dataset.projectReportSelection = key;
            input.dataset.selectionKind = kind;
            const text = document.createElement('span');
            text.className = 'project-report-selection-text';
            const titleEl = document.createElement('strong');
            titleEl.textContent = labelFn(item);
            const detailEl = document.createElement('small');
            detailEl.textContent = detailFn(item);
            text.append(titleEl, detailEl);
            row.append(input, text);
            group.appendChild(row);
          });
        }
        section.appendChild(group);
      });
      host.appendChild(section);
    }

    function renderPreview(st, host) {
      const section = document.createElement('section');
      section.className = 'project-report-preview';
      const header = document.createElement('div');
      header.className = 'project-report-preview-header';
      const heading = document.createElement('h3');
      heading.textContent = 'Preview';
      const actions = document.createElement('div');
      actions.className = 'project-report-actions';
      const previewBtn = button(st.previewing ? 'Previewing...' : 'Preview', 'Render preview', 'preview', 'secondary');
      previewBtn.disabled = !!st.previewing;
      const printBtn = button('Print/PDF', 'Print or save the preview as PDF', 'print', 'secondary');
      printBtn.disabled = !st.preview?.html;
      const exportBtn = button(st.exporting ? 'Exporting...' : 'Export archive', 'Export Markdown and HTML archive', 'export', 'primary');
      exportBtn.disabled = !!st.exporting;
      actions.append(previewBtn, printBtn, exportBtn);
      header.append(heading, actions);
      section.appendChild(header);
      if (st.preview && st.preview.html) {
        const frame = document.createElement('iframe');
        frame.className = 'project-report-preview-frame';
        frame.setAttribute('title', 'Report preview');
        frame.setAttribute('sandbox', '');
        frame.srcdoc = String(st.preview.html || '');
        section.appendChild(frame);
      } else {
        section.appendChild(ctx.emptyProjectPanel?.('Preview the report to render the current draft.') || document.createElement('div'));
      }
      host.appendChild(section);
    }

    function renderToolbar(st, host, projectId) {
      const toolbar = document.createElement('div');
      toolbar.className = 'project-report-toolbar';
      const saveBtn = button(st.saving ? 'Saving...' : 'Save draft', 'Save report draft', 'save', 'primary');
      saveBtn.disabled = st.saving || !canMutateProjects();
      if (!canMutateProjects()) saveBtn.title = deniedMessage();
      const reloadBtn = button('Reload saved', 'Reload saved report draft', 'reload');
      toolbar.append(saveBtn, reloadBtn);
      const status = document.createElement('span');
      status.className = 'project-report-dirty-state';
      status.textContent = st.dirty ? 'Unsaved changes' : (st.updated ? `Saved ${ctx.formatDate?.(st.updated) || st.updated}` : 'Not saved');
      toolbar.appendChild(status);
      host.appendChild(toolbar);
    }

    function renderReport(container, projectId, summary) {
      const st = stateFor(projectId);
      if (!st.loaded && !st.loading) {
        load(projectId, { render: false }).finally(() => {
          ctx.renderProjectExplorer?.();
        }).catch(() => {});
      }
      container.dataset.projectReportRoot = projectId;
      container.classList.add('project-report-root');
      if (st.loading) {
        container.appendChild(ctx.emptyProjectPanel?.('Loading report draft...') || document.createElement('div'));
        return;
      }
      const shell = document.createElement('div');
      shell.className = 'project-report-layout';
      renderNotice(st, shell);
      renderToolbar(st, shell, projectId);
      const editor = document.createElement('div');
      editor.className = 'project-report-editor nice-scroll';
      renderTemplates(st, editor);
      renderMetadata(st, editor);
      renderSections(st, editor);
      renderExportPrefs(st, editor);
      if (ensureFullSelectionItems(projectId, summary)) {
        renderSelection(st, editor, projectId, summary);
      } else {
        const selection = document.createElement('section');
        selection.className = 'project-report-panel project-report-selection';
        const heading = document.createElement('h3');
        heading.textContent = 'Included items';
        selection.append(heading, ctx.emptyProjectPanel?.('Loading full report item lists...') || document.createElement('div'));
        editor.appendChild(selection);
      }
      const previewHost = document.createElement('div');
      previewHost.className = 'project-report-preview-wrap';
      renderPreview(st, previewHost);
      shell.append(editor, previewHost);
      container.appendChild(shell);
      if (typeof global.enhanceAppSelects === 'function') global.enhanceAppSelects(container);
    }

    function renderMobileReportTab(projectId, summary) {
      const fragment = document.createDocumentFragment();
      const st = stateFor(projectId);
      const wrap = document.createElement('div');
      wrap.className = 'project-report-mobile';
      renderReport(wrap, projectId, summary);
      fragment.appendChild(wrap);
      return fragment;
    }

    function handleInput(event) {
      const root = event.target.closest?.('[data-project-report-root]');
      if (!root) return false;
      const projectId = String(root.dataset.projectReportRoot || '');
      const st = stateFor(projectId);
      syncEditableFields(st, root);
      markDirty(st, root);
      return true;
    }

    function handleChange(event) {
      const root = event.target.closest?.('[data-project-report-root]');
      if (!root) return false;
      const projectId = String(root.dataset.projectReportRoot || '');
      const st = stateFor(projectId);
      const template = event.target.closest?.('[data-project-report-template]');
      if (template) {
        applyTemplate(st, template.value);
        ctx.renderProjectExplorer?.();
        return true;
      }
      const selectionInput = event.target.closest?.('[data-project-report-selection]');
      if (selectionInput) {
        syncSelectionFromDom(st, root, String(selectionInput.dataset.projectReportSelection || ''));
        markDirty(st, root);
        return true;
      }
      syncEditableFields(st, root);
      const hadPreview = !!st.preview;
      markDirty(st, root);
      if (event.target.closest?.('[data-project-report-export]') && hadPreview) {
        ctx.renderProjectExplorer?.();
        preview(projectId, root).catch(() => {});
      }
      return true;
    }

    async function handleClick(event) {
      const actionEl = event.target.closest?.('[data-project-report-action]');
      if (!actionEl) return false;
      const root = actionEl.closest?.('[data-project-report-root]');
      if (!root) return false;
      event.preventDefault();
      const projectId = String(root.dataset.projectReportRoot || '');
      const st = stateFor(projectId);
      const action = String(actionEl.dataset.projectReportAction || '');
      if (action === 'save') await save(projectId, root);
      else if (action === 'preview') await preview(projectId, root);
      else if (action === 'export') await exportReport(projectId, root);
      else if (action === 'print') printReport(projectId);
      else if (action === 'reload') {
        if (st.dirty && !(await confirmReloadSavedDraft())) return true;
        stateByProject.delete(projectId);
        await load(projectId);
      } else if (action === 'section-up' || action === 'section-down') {
        moveSection(st, Number(actionEl.dataset.sectionIndex || 0), action === 'section-up' ? -1 : 1);
        ctx.renderProjectExplorer?.();
      } else if (action === 'selection-all' || action === 'selection-none') {
        const key = String(actionEl.dataset.selectionKey || '');
        root.querySelectorAll(`[data-project-report-selection="${key}"]`).forEach((input) => {
          input.checked = action === 'selection-all';
        });
        syncSelectionFromDom(st, root, key);
        if (st.draft.selection_modes && Object.prototype.hasOwnProperty.call(st.draft.selection_modes, key)) {
          st.draft.selection_modes[key] = 'manual';
        }
        markDirty(st, root);
        ctx.renderProjectExplorer?.();
      }
      return true;
    }

    return {
      load,
      renderReport,
      renderMobileReportTab,
      handleInput,
      handleChange,
      handleClick,
      stateFor,
      normalizeDraft,
    };
  }

  global.DarklabProjectReport = {
    createProjectReportController,
  };
})(globalThis);
