// Workflow catalog identity, lookup, and loading state.

function workflowSlug(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'workflow';
}

function workflowStorageKey(workflow) {
  const id = String(workflow?.id || '').trim();
  if (id) return id;
  const title = String(workflow?.title || '').trim();
  const description = String(workflow?.description || '').trim();
  return `${title}::${description}`;
}

function workflowLookupKeys(workflow) {
  const keys = [];
  const id = String(workflow?.id || '').trim();
  const title = String(workflow?.title || '').trim();
  [id, title, workflowSlug(title)].forEach((key) => {
    const value = String(key || '').trim().toLowerCase();
    if (value && !keys.includes(value)) keys.push(value);
  });
  return keys;
}

function workflowCliName(workflow) {
  const id = String(workflow?.id || '').trim();
  return workflowSlug(workflow?.title || id || 'workflow');
}

function createWorkflowCatalogStore({ apiFetch, onItems }) {
  let items = (
    typeof globalThis !== 'undefined' && Array.isArray(globalThis.__workflowCatalogItems)
  ) ? globalThis.__workflowCatalogItems.slice() : [];
  let loadPromise = null;

  const setItems = (nextItems) => {
    items = Array.isArray(nextItems) ? nextItems.slice() : [];
    if (typeof globalThis !== 'undefined') globalThis.__workflowCatalogItems = items.slice();
    return items;
  };

  const reload = async () => {
    const request = (async () => {
      const resp = await apiFetch('/workflows');
      if (resp && resp.ok === false) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      const nextItems = setItems(data.items || []);
      if (typeof onItems === 'function') onItems(nextItems);
      return nextItems;
    })();
    loadPromise = request;
    try {
      return await request;
    } finally {
      if (loadPromise === request) loadPromise = null;
    }
  };

  const ensureLoaded = () => (items.length ? Promise.resolve(items) : (loadPromise || reload()));

  const find = (selector) => {
    const query = String(selector || '').trim().toLowerCase();
    if (!query) return { workflow: null, error: 'workflow name is required' };
    const exactMatches = items.filter(item => workflowLookupKeys(item).some(key => key === query));
    if (exactMatches.length === 1) return { workflow: exactMatches[0], error: '' };
    if (exactMatches.length > 1) {
      return {
        workflow: null,
        error: `ambiguous workflow '${selector}': ${exactMatches.slice(0, 5).map(workflowCliName).join(', ')}`,
      };
    }
    const matches = items.filter(item => workflowLookupKeys(item).some(key => key.includes(query)));
    if (matches.length === 1) return { workflow: matches[0], error: '' };
    if (matches.length > 1) {
      return {
        workflow: null,
        error: `ambiguous workflow '${selector}': ${matches.slice(0, 5).map(workflowCliName).join(', ')}`,
      };
    }
    return { workflow: null, error: `workflow not found: ${selector}` };
  };

  return {
    ensureLoaded,
    find,
    getItems: () => items.slice(),
    reload,
    setItems,
  };
}

export {
  createWorkflowCatalogStore,
  workflowCliName,
  workflowLookupKeys,
  workflowSlug,
  workflowStorageKey,
};
