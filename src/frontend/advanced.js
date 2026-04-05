const workspaceSelect = document.getElementById('advanced-workspace-select');
let currentWorkspaceId = Number(window.localStorage.getItem('workspaceId')) || null;

function withWorkspace(url) {
  if (!currentWorkspaceId) return url;
  const query = `workspace_id=${encodeURIComponent(String(currentWorkspaceId))}`;
  return url.includes('?') ? `${url}&${query}` : `${url}?${query}`;
}

async function loadWorkspaces() {
  const [workspacesResponse, currentResponse] = await Promise.all([
    fetch('/workspaces'),
    fetch('/workspaces/current'),
  ]);
  if (!workspacesResponse.ok || !currentResponse.ok) {
    throw new Error('Failed to load workspaces');
  }

  const workspaces = await workspacesResponse.json();
  const current = await currentResponse.json();
  const knownWorkspaceIds = new Set(workspaces.map((workspace) => workspace.id));

  if (!currentWorkspaceId || !knownWorkspaceIds.has(currentWorkspaceId)) {
    currentWorkspaceId = current.id;
    window.localStorage.setItem('workspaceId', String(currentWorkspaceId));
  }

  workspaceSelect.innerHTML = '';
  workspaces.forEach((workspace) => {
    const option = document.createElement('option');
    option.value = String(workspace.id);
    option.textContent = workspace.name;
    option.selected = workspace.id === currentWorkspaceId;
    workspaceSelect.appendChild(option);
  });
}

async function switchWorkspace() {
  const nextWorkspaceId = Number(workspaceSelect.value);
  if (!nextWorkspaceId || nextWorkspaceId === currentWorkspaceId) return;
  const response = await fetch('/workspaces/switch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workspace_id: nextWorkspaceId }),
  });
  if (!response.ok) {
    throw new Error(`Workspace switch failed: ${response.status}`);
  }
  const workspace = await response.json();
  currentWorkspaceId = workspace.id;
  window.localStorage.setItem('workspaceId', String(currentWorkspaceId));
}

function buildTraversalRequest(form) {
  const method = form.dataset.method;
  const template = form.dataset.endpointTemplate;
  const responseEl = form.parentElement.querySelector('.response');
  const data = Object.fromEntries(new FormData(form).entries());

  let endpoint = template;
  Object.entries(data).forEach(([key, value]) => {
    endpoint = endpoint.replace(`{${key}}`, encodeURIComponent(String(value)));
  });

  if (method === 'GET') {
    const params = new URLSearchParams();
    Object.entries(data).forEach(([key, value]) => {
      if (template.includes(`{${key}}`) || value === '') return;
      params.set(key, value);
    });
    const query = params.toString();
    const url = query ? `${endpoint}?${query}` : endpoint;
    return { method, url: withWorkspace(url), responseEl };
  }

  const body = {};
  Object.entries(data).forEach(([key, value]) => {
    if (value === '') return;
    body[key] = Number.isNaN(Number(value)) ? value : Number(value);
  });
  return { method, url: withWorkspace(endpoint), body, responseEl };
}

function parseJsonField(value, fallback) {
  if (typeof value !== 'string' || value.trim() === '') return fallback;
  return JSON.parse(value);
}

function parseCommaSeparated(value) {
  if (typeof value !== 'string') return [];
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function buildEdgeCreationRequest(form) {
  const data = Object.fromEntries(new FormData(form).entries());
  const functionName = form.dataset.functionName;
  const responseEl = form.parentElement.querySelector('.response');

  const threshold = data.threshold === '' ? null : Number(data.threshold);
  const maxPairs = data.max_pairs === '' ? null : Number(data.max_pairs);
  const nodes = parseJsonField(data.nodes_json, []);
  const pairs = parseJsonField(data.pairs_json, []);
  const extra = parseJsonField(data.extra_json, {});
  const edgeTypesAllowed = parseCommaSeparated(data.edge_types_allowed);

  const request = {
    function_name: functionName,
    run_id: data.run_id || null,
    workspace_id: currentWorkspaceId,
    config: {
      threshold: Number.isNaN(threshold) ? null : threshold,
      max_pairs: Number.isNaN(maxPairs) ? null : maxPairs,
      edge_types_allowed: edgeTypesAllowed,
      extra,
    },
    nodes,
    pairs,
  };

  return {
    responseEl,
    url: withWorkspace(`/edge-creation/${functionName}`),
    body: request,
  };
}

async function submitForm(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const mode = form.dataset.mode || 'fetch';
  const responseEl = form.parentElement.querySelector('.response');
  responseEl.textContent = 'Loading...';

  try {
    if (mode === 'preview') {
      const request = buildEdgeCreationRequest(form);
      const response = await fetch(request.url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request.body),
      });
      const payload = await response.json().catch(() => null);
      request.responseEl.textContent = JSON.stringify(payload || { status: response.status }, null, 2);
      return;
    }

    const request = buildTraversalRequest(form);
    const response = await fetch(request.url, {
      method: request.method,
      headers: request.method === 'POST' ? { 'Content-Type': 'application/json' } : undefined,
      body: request.method === 'POST' ? JSON.stringify(request.body) : undefined,
    });
    const payload = await response.json().catch(() => null);
    request.responseEl.textContent = JSON.stringify(payload || { status: response.status }, null, 2);
  } catch (error) {
    responseEl.textContent = String(error);
  }
}

document.querySelectorAll('form').forEach((form) => {
  form.addEventListener('submit', submitForm);
});

workspaceSelect.addEventListener('change', () => {
  switchWorkspace().catch((error) => {
    window.alert(error.message);
  });
});

window.addEventListener('DOMContentLoaded', () => {
  loadWorkspaces().catch((error) => {
    window.alert(error.message);
  });
});
