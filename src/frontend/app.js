const svg = document.getElementById("graph-svg");
const graphCanvas = document.getElementById("graph-canvas");
const workspaceSelect = document.getElementById("workspace-select");
const pollTelegramButton = document.getElementById("poll-telegram-button");
const generateEdgesButton = document.getElementById("generate-edges-button");
const narrativeModeButton = document.getElementById("narrative-mode-button");
const pathTracingButton = document.getElementById("path-tracing-button");
const toggleAddNodeButton = document.getElementById("toggle-add-node-button");
const addNodeSheet = document.getElementById("add-node-sheet");
const reviewLinksButton = document.getElementById("review-links-button");
const developerModeButton = document.getElementById("developer-mode-button");
const developerModeStatus = document.getElementById("developer-mode-status");
const themeToggleButton = document.getElementById("theme-toggle-button");
const exportGraphButton = document.getElementById("export-graph-button");
const emptyState = document.getElementById("empty-state");
const nodeDetail = document.getElementById("node-detail");
const detailRaw = document.getElementById("detail-raw");
const detailTagsHeading = document.getElementById("detail-tags-heading");
const detailTags = document.getElementById("detail-tags");
const detailNarrativeSection = document.getElementById("detail-narrative-section");
const detailNarrative = document.getElementById("detail-narrative");
const createNodeHeading = document.getElementById("create-node-heading");
const createNodeForm = document.getElementById("create-node-form");
const createNodeText = document.getElementById("create-node-text");
const createNodeTimeWrap = document.getElementById("create-node-time-wrap");
const createNodeTime = document.getElementById("create-node-time");
const createNodeSubmit = document.getElementById("create-node-submit");
const edgeFormSheet = document.getElementById("edge-form-sheet");
const edgeSelectionSummary = document.getElementById("edge-selection-summary");
const createEdgeForm = document.getElementById("create-edge-form");
const createEdgeType = document.getElementById("create-edge-type");
const createEdgeWeight = document.getElementById("create-edge-weight");
const edgeWeightDisplay = document.getElementById("edge-weight-display");
const createEdgeSubmit = document.getElementById("create-edge-submit");
const proposalOverlay = document.getElementById("proposal-overlay");
const closeProposalsButton = document.getElementById("close-proposals-button");
const proposalList = document.getElementById("proposal-list");
const detailSaveButton = document.getElementById("detail-save-button");
const detailTagInput = document.getElementById("detail-tag-input");
const detailTagAdd = document.getElementById("detail-tag-add");

let activeNodeId = null;
let currentData = { nodes: [], edges: [] };
let setupReady = false;
let developerMode = window.localStorage.getItem("developerMode") === "on";
let currentTheme = window.localStorage.getItem("theme") || "light";

// Token-based auth — read from URL param on load, persist in localStorage
(function initToken() {
  const urlToken = new URLSearchParams(window.location.search).get("token");
  if (urlToken) {
    window.localStorage.setItem("authToken", urlToken);
    const url = new URL(window.location.href);
    url.searchParams.delete("token");
    window.history.replaceState({}, "", url.toString());
  }
  if (!window.localStorage.getItem("authToken")) {
    window.location.href = "/login";
  }
})();
const authToken = window.localStorage.getItem("authToken");

let currentWorkspaceId = Number(window.localStorage.getItem("workspaceId")) || null;
let currentWorkspaceName = null;
let currentWorkspaceType = null;
let edgeSourceNodeId = null;
let edgeTargetNodeId = null;
let graphZoom = Number(window.localStorage.getItem("graphZoom")) || 1;
let panX = 0;
let panY = 0;
let graphNeedsCenter = true;
let narrativeMode = false;
let narrativeNodeId = null;
let narrativeText = "";
let narrativeLoading = false;
let narrativeError = "";
let pathTracingMode = false;
let tracedRootNodeId = null;
let tracedNodeIds = new Set();
let tracedEdgeIds = new Set();

const nodePositions = new Map();
let dragNodeId = null;
let dragOffsetX = 0;
let dragOffsetY = 0;
let dragHasMoved = false;
let justDragged = false;

const NOTE_BACKGROUNDS = [
  { base: "#fffdf8", overlay: null },
  { base: "#f8f2e9", overlay: "note-lines" },
  { base: "#f5ecde", overlay: null },
  { base: "#f0e5d5", overlay: "note-grid" },
  { base: "#f9f4ec", overlay: "note-lines" },
  { base: "#f6efe5", overlay: "note-grid" },
];

const NOTE_BACKGROUNDS_DARK = [
  { base: "#1e1a13", overlay: null },
  { base: "#1c1910", overlay: "note-lines" },
  { base: "#1a1710", overlay: null },
  { base: "#18150e", overlay: "note-grid" },
  { base: "#1d1b11", overlay: "note-lines" },
  { base: "#1b180f", overlay: "note-grid" },
];

const NOTE_BACKGROUNDS_COLORFUL = [
  { base: "rgba(255, 253, 248, 0.84)", overlay: null },
  { base: "rgba(248, 242, 233, 0.84)", overlay: "note-lines" },
  { base: "rgba(245, 236, 222, 0.84)", overlay: null },
  { base: "rgba(240, 229, 213, 0.84)", overlay: "note-grid" },
  { base: "rgba(249, 244, 236, 0.84)", overlay: "note-lines" },
  { base: "rgba(246, 239, 229, 0.84)", overlay: "note-grid" },
];

function setButtonsDisabled(disabled) {
  workspaceSelect.disabled = disabled;
  pollTelegramButton.disabled = disabled;
  generateEdgesButton.disabled = disabled;
  narrativeModeButton.disabled = disabled;
  pathTracingButton.disabled = disabled;
  reviewLinksButton.disabled = disabled;
  createNodeSubmit.disabled = disabled;
  createEdgeSubmit.disabled = disabled;
}

function tokenQuery() {
  return authToken ? `token=${encodeURIComponent(authToken)}` : "";
}

function withToken(url) {
  const query = tokenQuery();
  if (!query) return url;
  return url.includes("?") ? `${url}&${query}` : `${url}?${query}`;
}

function workspaceQuery() {
  const parts = [];
  if (currentWorkspaceId) parts.push(`workspace_id=${encodeURIComponent(String(currentWorkspaceId))}`);
  if (authToken) parts.push(`token=${encodeURIComponent(authToken)}`);
  return parts.join("&");
}

function withWorkspace(url) {
  const query = workspaceQuery();
  if (!query) return url;
  return url.includes("?") ? `${url}&${query}` : `${url}?${query}`;
}

async function loadWorkspaces() {
  const [workspacesResponse, currentResponse] = await Promise.all([
    fetch(withToken("/workspaces")),
    fetch(withToken("/workspaces/current")),
  ]);
  if (!workspacesResponse.ok || !currentResponse.ok) {
    throw new Error("Failed to load workspaces");
  }

  const workspaces = await workspacesResponse.json();
  const current = await currentResponse.json();
  const knownWorkspaceIds = new Set(workspaces.map((workspace) => workspace.id));

  if (!currentWorkspaceId || !knownWorkspaceIds.has(currentWorkspaceId)) {
    currentWorkspaceId = current.id;
    window.localStorage.setItem("workspaceId", String(currentWorkspaceId));
  }
  if (currentWorkspaceId === current.id) {
    currentWorkspaceName = current.display_name || current.name;
    currentWorkspaceType = current.type;
  }

  workspaceSelect.innerHTML = "";
  workspaces.forEach((workspace) => {
    const option = document.createElement("option");
    option.value = String(workspace.id);
    option.textContent = workspace.display_name || workspace.name;
    option.selected = workspace.id === currentWorkspaceId;
    workspaceSelect.appendChild(option);
  });
}

function parseInlineTags(text) {
  const tags = [];
  const seen = new Set();
  const stripped = String(text || "").replace(/(?<!\w)#([A-Za-z][A-Za-z0-9_-]*)/g, (_, rawTag) => {
    const tag = rawTag.toLowerCase();
    if (!seen.has(tag)) {
      seen.add(tag);
      tags.push(tag);
    }
    return "";
  });
  return {
    rawText: stripped.replace(/\s+/g, " ").trim(),
    tags,
  };
}

function updateCreateNodeForm() {
  const isTimeAware = currentWorkspaceType === "time_aware";
  createNodeHeading.textContent = isTimeAware ? "Add Timed Node" : "Add Node";
  createNodeTimeWrap.classList.toggle("hidden", !isTimeAware);
  createNodeTime.required = isTimeAware;
}

function updateNarrativeModeButton() {
  narrativeModeButton.setAttribute("aria-pressed", narrativeMode ? "true" : "false");
  narrativeModeButton.classList.toggle("is-active", narrativeMode);
}

function updatePathTracingButton() {
  pathTracingButton.setAttribute("aria-pressed", pathTracingMode ? "true" : "false");
  pathTracingButton.classList.toggle("is-active", pathTracingMode);
}

function clampZoom(value) {
  return Math.max(0.12, Math.min(12, value));
}

function setGraphZoom(value) {
  graphZoom = clampZoom(value);
  window.localStorage.setItem("graphZoom", String(graphZoom));
}

function edgeSelectionNode(nodeId) {
  return currentData.nodes.find((node) => node.id === nodeId) || null;
}

function nodePreview(nodeId) {
  const node = edgeSelectionNode(nodeId);
  if (!node) return "none";
  const text = String(node.raw_text || "").trim();
  return text;
}

function updateEdgeSelectionUi() {
  if (!edgeSourceNodeId && !edgeTargetNodeId) {
    edgeFormSheet.classList.add("hidden");
    edgeSelectionSummary.textContent = "Select two nodes.";
    return;
  }

  edgeFormSheet.classList.remove("hidden");

  if (!edgeSourceNodeId) {
    edgeSelectionSummary.textContent = "Click the first node to set the source.";
  } else if (!edgeTargetNodeId) {
    edgeSelectionSummary.textContent = `Source: ${nodePreview(edgeSourceNodeId)}. Click the second node to set the target.`;
  } else {
    edgeSelectionSummary.textContent = `Source: ${nodePreview(edgeSourceNodeId)} → Target: ${nodePreview(edgeTargetNodeId)}`;
  }
}

function resetEdgeSelection() {
  edgeSourceNodeId = null;
  edgeTargetNodeId = null;
  updateEdgeSelectionUi();
}

function clearPathTrace() {
  tracedRootNodeId = null;
  tracedNodeIds = new Set();
  tracedEdgeIds = new Set();
}

function computeDescendants(rootNodeId) {
  const adjacency = new Map();
  currentData.edges.forEach((edge) => {
    const neighbors = adjacency.get(edge.from_node_id) || [];
    neighbors.push(edge);
    adjacency.set(edge.from_node_id, neighbors);
  });

  const visited = new Set([rootNodeId]);
  const queue = [rootNodeId];
  const descendants = new Set();
  const edgeIds = new Set();

  while (queue.length > 0) {
    const current = queue.shift();
    const children = adjacency.get(current) || [];
    children.forEach((edge) => {
      const childId = edge.to_node_id;
      if (visited.has(childId)) return;
      visited.add(childId);
      descendants.add(childId);
      edgeIds.add(edge.id);
      queue.push(childId);
    });
  }

  return { descendants, edgeIds };
}

function activeTagValues(node) {
  if (!developerMode) return node.tags || [];

  const linkerTags = node.linker_tags || {};
  return [
    ...(linkerTags.keywords || []).map((value) => `keyword:${value}`),
    ...(linkerTags.concepts || []).map((value) => `concept:${value}`),
  ];
}

function makeEditableTag(value) {
  const tag = document.createElement("span");
  tag.className = "tag";
  tag.dataset.tag = value;
  tag.textContent = value;
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "tag-remove";
  remove.textContent = "×";
  remove.addEventListener("click", () => tag.remove());
  tag.appendChild(remove);
  return tag;
}

function renderTags(values, emptyLabel) {
  detailTags.innerHTML = "";
  const editable = !developerMode;

  if (!values || values.length === 0) {
    if (!editable) {
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = emptyLabel;
      detailTags.appendChild(tag);
    }
    return;
  }

  values.forEach((value) => {
    if (editable) {
      detailTags.appendChild(makeEditableTag(value));
    } else {
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = value;
      detailTags.appendChild(tag);
    }
  });
}

const THEME_CYCLE = ["light", "dark", "colorful"];
const THEME_NEXT_LABEL = { light: "Dark", dark: "Colorful", colorful: "Light" };

function applyTheme() {
  document.documentElement.dataset.theme = currentTheme === "light" ? "" : currentTheme;
  themeToggleButton.textContent = THEME_NEXT_LABEL[currentTheme] || "Dark";
}

function toggleTheme() {
  const idx = THEME_CYCLE.indexOf(currentTheme);
  currentTheme = THEME_CYCLE[(idx + 1) % THEME_CYCLE.length];
  window.localStorage.setItem("theme", currentTheme);
  applyTheme();
  if (currentData.nodes.length > 0) renderGraph(currentData);
}

function updateDeveloperModeButton() {
  developerModeButton.textContent = developerMode ? "Developer Mode On" : "Developer Mode Off";
  developerModeButton.setAttribute("aria-pressed", developerMode ? "true" : "false");
  developerModeButton.classList.toggle("action-toggle-on", developerMode);
  developerModeStatus.textContent = developerMode ? "showing linker tags" : "showing user tags";
}

function showStatusMessage(message) {
  clearSvg();
  emptyState.classList.remove("hidden");
  nodeDetail.classList.add("hidden");
  emptyState.textContent = message;
}

function forceLayout(nodes, edges, width, height) {
  if (nodes.length === 0) return nodes;

  const positions = polarLayout(nodes, width, height).map((n) => ({
    id: n.id,
    x: n.x,
    y: n.y,
    vx: 0,
    vy: 0,
    fx: 0,
    fy: 0,
  }));

  const posMap = new Map(positions.map((p) => [p.id, p]));
  const cx = width / 2;
  const cy = height / 2;
  const repulsion = 28000;
  const attraction = 0.018;
  const centerStrength = 0.004;
  const damping = 0.82;
  const iterations = 320;

  for (let i = 0; i < iterations; i++) {
    positions.forEach((p) => { p.fx = 0; p.fy = 0; });

    for (let a = 0; a < positions.length; a++) {
      for (let b = a + 1; b < positions.length; b++) {
        const pa = positions[a];
        const pb = positions[b];
        const dx = pb.x - pa.x || 0.1;
        const dy = pb.y - pa.y || 0.1;
        const dist = Math.max(Math.hypot(dx, dy), 1);
        // hard push if closer than minimum distance
        const minDist = 240;
        const effectiveDist = dist < minDist ? minDist * 0.5 : dist;
        const force = repulsion / (effectiveDist * effectiveDist);
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        pa.fx -= fx;
        pa.fy -= fy;
        pb.fx += fx;
        pb.fy += fy;
      }
    }

    edges.forEach((edge) => {
      const pa = posMap.get(edge.from_node_id);
      const pb = posMap.get(edge.to_node_id);
      if (!pa || !pb) return;
      const dx = pb.x - pa.x;
      const dy = pb.y - pa.y;
      const dist = Math.max(Math.hypot(dx, dy), 1);
      // only attract if further than ideal edge length
      const idealLength = 280;
      if (dist < idealLength) return;
      const force = attraction * (dist - idealLength);
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      pa.fx += fx;
      pa.fy += fy;
      pb.fx -= fx;
      pb.fy -= fy;
    });

    positions.forEach((p) => {
      p.fx += (cx - p.x) * centerStrength;
      p.fy += (cy - p.y) * centerStrength;
      p.vx = (p.vx + p.fx) * damping;
      p.vy = (p.vy + p.fy) * damping;
      p.x += p.vx;
      p.y += p.vy;
    });
  }

  return nodes.map((node) => ({
    ...node,
    x: posMap.get(node.id)?.x ?? cx,
    y: posMap.get(node.id)?.y ?? cy,
  }));
}

function polarLayout(nodes, width, height) {
  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.max(Math.min(width, height) * 0.34, 130);

  return nodes.map((node, index) => {
    const angle = (index / Math.max(nodes.length, 1)) * Math.PI * 2;
    const orbital = radius + (index % 5) * 26;
    return {
      ...node,
      x: centerX + Math.cos(angle) * orbital,
      y: centerY + Math.sin(angle) * orbital,
    };
  });
}

function timeAwareNodes(nodes) {
  return nodes
    .map((node, index) => ({
      ...node,
      _year: Number(node.time && node.time.year),
      _originalIndex: index,
    }))
    .filter((node) => Number.isFinite(node._year));
}

function timelineLayout(nodes, width, height) {
  const nodesWithYear = timeAwareNodes(nodes);
  if (nodesWithYear.length === 0) {
    return { nodes: polarLayout(nodes, width, height), years: [], contentHeight: height };
  }

  const years = [...new Set(nodesWithYear.map((node) => node._year))].sort((a, b) => a - b);
  const leftPadding = 120;
  const rightPadding = 80;
  const topPadding = 90;
  const bottomPadding = 80;
  const usableWidth = Math.max(1, width - leftPadding - rightPadding);
  const yearGroups = new Map();
  const rowGap = 26;
  let maxColumnBottom = topPadding;

  nodesWithYear
    .sort((left, right) => left._year - right._year || left._originalIndex - right._originalIndex)
    .forEach((node) => {
      const yearNodes = yearGroups.get(node._year) || [];
      yearNodes.push(node);
      yearGroups.set(node._year, yearNodes);
    });

  const positioned = [];
  years.forEach((year, yearIndex) => {
    const group = yearGroups.get(year) || [];
    const x =
      years.length === 1
        ? leftPadding + usableWidth / 2
        : leftPadding + (usableWidth * yearIndex) / (years.length - 1);
    let cursorY = topPadding;
    group.forEach((node, index) => {
      const size = getNoteSize(node);
      const centerY = cursorY + size.height / 2;
      positioned.push({
        ...node,
        x,
        y: centerY,
      });
      cursorY += size.height + rowGap;
    });
    maxColumnBottom = Math.max(maxColumnBottom, cursorY - rowGap);
  });

  const positionedIds = new Set(positioned.map((node) => node.id));
  const undated = nodes.filter((node) => !positionedIds.has(node.id));
  const contentHeight = Math.max(height, maxColumnBottom + bottomPadding);
  const undatedLayout = polarLayout(undated, width, contentHeight).map((node, index) => ({
    ...node,
    x: width - 140 - (index % 2) * 60,
    y: topPadding + 40 + index * 110,
  }));

  return {
    nodes: [...positioned, ...undatedLayout],
    years,
    contentHeight,
    axis: {
      leftPadding,
      rightPadding,
      topY: 44,
    },
  };
}

function timelineContentWidth(viewportWidth, years) {
  if (!years || years.length === 0) return viewportWidth;
  const baseWidth = 220;
  const padded = 220 + years.length * baseWidth;
  return Math.max(viewportWidth, padded);
}

function renderTimelineAxis(layout, width) {
  if (!layout.axis || !layout.years || layout.years.length === 0) return;

  const axis = svgEl("line", {
    x1: layout.axis.leftPadding,
    y1: layout.axis.topY,
    x2: width - layout.axis.rightPadding,
    y2: layout.axis.topY,
    stroke: "rgba(95, 81, 68, 0.34)",
    "stroke-width": 1.2,
  });
  svg.appendChild(axis);

  layout.years.forEach((year, index) => {
    const x =
      layout.years.length === 1
        ? layout.axis.leftPadding + (width - layout.axis.leftPadding - layout.axis.rightPadding) / 2
        : layout.axis.leftPadding +
          ((width - layout.axis.leftPadding - layout.axis.rightPadding) * index) / (layout.years.length - 1);
    svg.appendChild(
      svgEl("line", {
        x1: x,
        y1: layout.axis.topY - 8,
        x2: x,
        y2: layout.axis.topY + 8,
        stroke: "rgba(95, 81, 68, 0.28)",
        "stroke-width": 1,
      }),
    );
    const label = svgEl("text", {
      x,
      y: layout.axis.topY - 16,
      class: "edge-label",
      "text-anchor": "middle",
    });
    label.textContent = String(year);
    svg.appendChild(label);
  });
}

function clearSvg() {
  while (svg.firstChild) {
    svg.removeChild(svg.firstChild);
  }
}

function svgEl(name, attrs = {}) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attrs).forEach(([key, value]) => {
    element.setAttribute(key, String(value));
  });
  return element;
}

function ensureDefs() {
  const defs = svgEl("defs");

  const lines = svgEl("pattern", {
    id: "note-lines",
    width: 16,
    height: 16,
    patternUnits: "userSpaceOnUse",
  });
  lines.appendChild(svgEl("line", {
    x1: 0,
    y1: 13,
    x2: 16,
    y2: 13,
    stroke: "rgba(128, 103, 77, 0.14)",
    "stroke-width": 1,
  }));
  defs.appendChild(lines);

  const grid = svgEl("pattern", {
    id: "note-grid",
    width: 18,
    height: 18,
    patternUnits: "userSpaceOnUse",
  });
  grid.appendChild(svgEl("rect", {
    x: 0,
    y: 0,
    width: 18,
    height: 18,
    fill: "none",
    stroke: "rgba(128, 103, 77, 0.12)",
    "stroke-width": 1,
  }));
  defs.appendChild(grid);

  svg.appendChild(defs);
}

function wrapText(text, maxCharsPerLine = 22) {
  const words = String(text || "").trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return ["untitled"];

  const lines = [];
  let current = "";

  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length <= maxCharsPerLine) {
      current = next;
      continue;
    }

    if (current) lines.push(current);
    current = word;
  }

  if (current) lines.push(current);

  return lines;
}

function getNoteSize(node) {
  const length = (node.raw_text || node.label || "").length;
  const width = length > 240 ? 206 : 178;
  const lines = wrapText(node.raw_text || node.label || "");
  const minHeight = 86;
  const bodyHeight = 26 + lines.length * 20;
  const extra = length > 240 ? 26 : length > 140 ? 12 : 0;
  return { width, height: Math.max(minHeight, bodyHeight + extra), lines };
}

function getNoteStyle(node) {
  const theme = document.documentElement.dataset.theme;
  const set = theme === "dark" ? NOTE_BACKGROUNDS_DARK
    : theme === "colorful" ? NOTE_BACKGROUNDS_COLORFUL
    : NOTE_BACKGROUNDS;
  return set[node.id % set.length];
}

function buildSlackPath(from, to) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const distance = Math.hypot(dx, dy);
  const sag = Math.max(20, Math.min(54, distance * 0.15));
  return `M ${from.x} ${from.y} C ${from.x + dx * 0.3} ${from.y + sag}, ${from.x + dx * 0.7} ${to.y + sag}, ${to.x} ${to.y}`;
}

function renderDetail(node) {
  activeNodeId = node.id;
  emptyState.classList.add("hidden");
  nodeDetail.classList.remove("hidden");
  detailRaw.value = node.raw_text;
  detailRaw.style.height = "auto";
  detailRaw.style.height = `${detailRaw.scrollHeight}px`;
  detailTagsHeading.textContent = developerMode ? "Linker Tags" : "Tags";
  renderTags(activeTagValues(node), developerMode ? "no linker tags" : "untagged");
  detailTagAdd.classList.toggle("hidden", developerMode);
  detailSaveButton.classList.toggle("hidden", developerMode);
  const hasNarrative = narrativeNodeId === node.id && (narrativeLoading || narrativeError || narrativeText);
  detailNarrativeSection.classList.toggle("hidden", !hasNarrative);
  if (hasNarrative) {
    if (narrativeLoading) {
      detailNarrative.textContent = "Generating short narrative...";
    } else if (narrativeError) {
      detailNarrative.textContent = narrativeError;
    } else {
      detailNarrative.textContent = narrativeText;
    }
  } else {
    detailNarrative.textContent = "";
  }

  document.querySelectorAll(".node-card").forEach((card) => {
    const cardNodeId = Number(card.dataset.nodeId);
    const isBaseCard = !card.classList.contains("pattern");
    card.classList.toggle("is-active", isBaseCard && cardNodeId === node.id);
    card.classList.toggle("is-edge-source", isBaseCard && cardNodeId === edgeSourceNodeId);
    card.classList.toggle("is-edge-target", isBaseCard && cardNodeId === edgeTargetNodeId);
    card.classList.toggle("is-trace-root", isBaseCard && cardNodeId === tracedRootNodeId);
    card.classList.toggle("is-traced", isBaseCard && tracedNodeIds.has(cardNodeId));
  });
}

function handleNodeSelection(node) {
  activeNodeId = node.id;

  if (narrativeMode) {
    generateNarrativeForNode(node.id).catch((error) => {
      narrativeNodeId = node.id;
      narrativeLoading = false;
      narrativeText = "";
      narrativeError = error.message;
      renderGraph(currentData);
    });
  }

  if (pathTracingMode) {
    tracedRootNodeId = node.id;
    const trace = computeDescendants(node.id);
    tracedNodeIds = trace.descendants;
    tracedEdgeIds = trace.edgeIds;
    renderGraph(currentData);
    return;
  }

  if (!edgeSourceNodeId) {
    edgeSourceNodeId = node.id;
    edgeTargetNodeId = null;
    renderDetail(node);
    updateEdgeSelectionUi();
    return;
  }

  if (node.id === edgeSourceNodeId) {
    edgeSourceNodeId = null;
    edgeTargetNodeId = null;
    renderDetail(node);
    updateEdgeSelectionUi();
    return;
  }

  edgeTargetNodeId = node.id;
  renderDetail(node);
  updateEdgeSelectionUi();
}

function startNodeDrag(e, node) {
  if (e.button !== 0) return;
  e.stopPropagation();
  dragNodeId = node.id;
  dragHasMoved = false;
  const rect = graphCanvas.getBoundingClientRect();
  const svgX = (e.clientX - rect.left - panX) / graphZoom;
  const svgY = (e.clientY - rect.top - panY) / graphZoom;
  const pos = nodePositions.get(node.id) || { x: node.x, y: node.y };
  dragOffsetX = svgX - pos.x;
  dragOffsetY = svgY - pos.y;
}

async function saveNodePosition(nodeId, x, y) {
  await fetch(withWorkspace(`/nodes/${nodeId}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ metadata_json: { ui_position: { x, y } } }),
  });
}

function applyDragPosition(nodeId, x, y) {
  nodePositions.set(nodeId, { x, y });
  const group = svg.querySelector(`g[data-node-id="${nodeId}"]`);
  if (group) group.setAttribute("transform", `translate(${x} ${y})`);
  svg.querySelectorAll(`path[data-edge-from="${nodeId}"], path[data-edge-to="${nodeId}"]`).forEach((path) => {
    const fromId = Number(path.dataset.edgeFrom);
    const toId = Number(path.dataset.edgeTo);
    const fromPos = nodePositions.get(fromId);
    const toPos = nodePositions.get(toId);
    if (fromPos && toPos) path.setAttribute("d", buildSlackPath(fromPos, toPos));
  });
}

function renderGraph(data) {
  currentData = data;
  clearSvg();
  ensureDefs();

  const width = graphCanvas.clientWidth;
  const height = graphCanvas.clientHeight;

  const isTimeAware = data.workspace && data.workspace.type === "time_aware";
  const initialTimeline = isTimeAware ? timelineLayout(data.nodes, width, height) : null;
  const baseContentWidth = initialTimeline ? timelineContentWidth(width, initialTimeline.years) : width;
  const timeline = initialTimeline ? timelineLayout(data.nodes, baseContentWidth, height) : null;
  const baseContentHeight = timeline ? timeline.contentHeight : height;
  const layoutNodes = timeline ? timeline.nodes : forceLayout(data.nodes, data.edges, baseContentWidth, baseContentHeight);

  const hasStoredPositions = nodePositions.size > 0 || data.nodes.some((n) => n.ui_position);
  let contentWidth = baseContentWidth;
  let contentHeight = baseContentHeight;
  if (!timeline && layoutNodes.length > 0) {
    const pad = 140;
    if (!hasStoredPositions) {
      // Fresh load, no saved positions: normalize bounding box and store.
      const minX = Math.min(...layoutNodes.map((n) => n.x)) - pad;
      const maxX = Math.max(...layoutNodes.map((n) => n.x)) + pad;
      const minY = Math.min(...layoutNodes.map((n) => n.y)) - pad;
      const maxY = Math.max(...layoutNodes.map((n) => n.y)) + pad;
      contentWidth = Math.max(width, maxX - minX);
      contentHeight = Math.max(height, maxY - minY);
      layoutNodes.forEach((n) => { n.x -= minX; n.y -= minY; });
      layoutNodes.forEach((n) => nodePositions.set(n.id, { x: n.x, y: n.y }));
    } else {
      // Use in-memory positions, fall back to db-saved positions, then force layout for new nodes.
      layoutNodes.forEach((n) => {
        if (nodePositions.has(n.id)) {
          const pos = nodePositions.get(n.id);
          n.x = pos.x;
          n.y = pos.y;
        } else if (n.ui_position) {
          n.x = n.ui_position.x;
          n.y = n.ui_position.y;
          nodePositions.set(n.id, { x: n.x, y: n.y });
        } else {
          nodePositions.set(n.id, { x: n.x, y: n.y });
        }
      });
      const maxX = Math.max(...layoutNodes.map((n) => n.x)) + pad;
      const maxY = Math.max(...layoutNodes.map((n) => n.y)) + pad;
      contentWidth = Math.max(width, maxX);
      contentHeight = Math.max(height, maxY);
    }
  }

  svg.setAttribute("viewBox", `0 0 ${contentWidth} ${contentHeight}`);
  svg.style.width = `${contentWidth}px`;
  svg.style.height = `${contentHeight}px`;
  svg.style.minWidth = `${contentWidth}px`;

  if (graphNeedsCenter) {
    setGraphZoom(1);
    panX = (width - contentWidth) / 2;
    panY = (height - contentHeight) / 2;
    graphNeedsCenter = false;
  }

  svg.style.transformOrigin = "0 0";
  svg.style.transform = `translate(${panX}px, ${panY}px) scale(${graphZoom})`;
  const nodeMap = new Map(layoutNodes.map((node) => [node.id, node]));

  if (timeline) {
    renderTimelineAxis(timeline, baseContentWidth);
  }

  data.edges.forEach((edge) => {
    const from = nodeMap.get(edge.from_node_id);
    const to = nodeMap.get(edge.to_node_id);
    if (!from || !to) return;

    const pathD = buildSlackPath(from, to);
    const line = svgEl("path", {
      d: pathD,
      class: "edge",
      "stroke-width": Math.max(1.2, edge.weight * 2.6),
      "data-edge-from": edge.from_node_id,
      "data-edge-to": edge.to_node_id,
    });
    if (tracedEdgeIds.has(edge.id)) line.classList.add("is-traced");
    svg.appendChild(line);

    const label = svgEl("text", {
      x: (from.x + to.x) / 2,
      y: (from.y + to.y) / 2 + Math.max(12, Math.min(26, Math.hypot(to.x - from.x, to.y - from.y) * 0.06)),
      class: "edge-label",
      "text-anchor": "middle",
    });
    label.textContent = edge.type.replaceAll("_", " ");
    svg.appendChild(label);
  });

  layoutNodes.forEach((node) => {
    const group = svgEl("g", {
      transform: `translate(${node.x} ${node.y})`,
      style: "cursor:pointer",
      "data-node-id": node.id,
    });

    const size = getNoteSize(node);
    const style = getNoteStyle(node);

    const base = svgEl("rect", {
      x: -size.width / 2,
      y: -size.height / 2,
      width: size.width,
      height: size.height,
      rx: 8,
      ry: 8,
      class: "node-card",
      fill: style.base,
      "data-node-id": node.id,
    });
    if (activeNodeId === node.id) base.classList.add("is-active");
    if (edgeSourceNodeId === node.id) base.classList.add("is-edge-source");
    if (edgeTargetNodeId === node.id) base.classList.add("is-edge-target");
    if (tracedRootNodeId === node.id) base.classList.add("is-trace-root");
    if (tracedNodeIds.has(node.id)) base.classList.add("is-traced");
    group.appendChild(base);

    if (style.overlay) {
      group.appendChild(svgEl("rect", {
        x: -size.width / 2,
        y: -size.height / 2,
        width: size.width,
        height: size.height,
        rx: 8,
        ry: 8,
        class: "node-card pattern",
        fill: `url(#${style.overlay})`,
        opacity: 0.62,
        "data-node-id": `${node.id}-pattern`,
      }));
    }

    if (node.type === "topic") {
      const stamp = svgEl("text", {
        x: -size.width / 2 + 14,
        y: -size.height / 2 + 16,
        class: "topic-stamp",
      });
      stamp.textContent = "TOPIC";
      group.appendChild(stamp);
    }

    const label = svgEl("text", {
      x: -size.width / 2 + 14,
      y: -size.height / 2 + 24,
      class: "node-label",
    });

    size.lines.forEach((line, index) => {
      const tspan = svgEl("tspan", {
        x: -size.width / 2 + 14,
        dy: index === 0 ? 0 : 19,
      });
      tspan.textContent = line;
      label.appendChild(tspan);
    });

    group.appendChild(label);
    group.addEventListener("mousedown", (e) => startNodeDrag(e, node));
    group.addEventListener("click", () => {
      if (justDragged) { justDragged = false; return; }
      handleNodeSelection(node);
    });
    svg.appendChild(group);
  });

  if (!activeNodeId && layoutNodes.length > 0) {
    renderDetail(layoutNodes[0]);
  }
  updateEdgeSelectionUi();
}

async function loadGraph() {
  if (!setupReady) return;
  setButtonsDisabled(true);
  try {
    const response = await fetch(withWorkspace("/graph-data"));
    if (!response.ok) throw new Error(`Failed to load graph data: ${response.status}`);
    const data = await response.json();
    currentWorkspaceName = data.workspace ? data.workspace.name : currentWorkspaceName;
    currentWorkspaceType = data.workspace ? data.workspace.type : currentWorkspaceType;
    updateCreateNodeForm();
    renderGraph(data);
  } catch (error) {
    clearSvg();
    emptyState.classList.remove("hidden");
    nodeDetail.classList.add("hidden");
    emptyState.textContent = error.message;
  } finally {
    setButtonsDisabled(false);
  }
}

async function waitForSetup() {
  setButtonsDisabled(true);
  showStatusMessage("Setting up embedding model...");

  const maxRetries = 10;
  let retries = 0;

  while (true) {
    const response = await fetch("/setup-status");
    if (!response.ok) {
      showStatusMessage(`Setup status failed: ${response.status}`);
      return;
    }

    const payload = await response.json();
    if (payload.status === "ready") {
      setupReady = true;
      await loadWorkspaces();
      await loadGraph();
      return;
    }

    if (payload.status === "error") {
      showStatusMessage(payload.detail || "Embedding setup failed.");
      return;
    }

    retries += 1;
    if (retries >= maxRetries) {
      showStatusMessage("Something went wrong, please refresh.");
      return;
    }

    showStatusMessage(payload.detail || "Setting up embedding model...");
    await new Promise((resolve) => window.setTimeout(resolve, 1500));
  }
}

async function pollTelegram() {
  if (!setupReady) return;
  setButtonsDisabled(true);
  try {
    const response = await fetch("/telegram/poll", { method: "POST" });
    if (!response.ok) throw new Error(`Telegram poll failed: ${response.status}`);
    const payload = await response.json();
    if (payload.current_workspace_id && payload.current_workspace_id !== currentWorkspaceId) {
      currentWorkspaceId = payload.current_workspace_id;
      currentWorkspaceName = payload.current_workspace_name;
      window.localStorage.setItem("workspaceId", String(currentWorkspaceId));
      await loadWorkspaces();
    }
    await loadGraph();
  } catch (error) {
    emptyState.classList.remove("hidden");
    nodeDetail.classList.add("hidden");
    emptyState.textContent = error.message;
    setButtonsDisabled(false);
  }
}

async function generateEdges() {
  if (!setupReady) return;
  setButtonsDisabled(true);
  try {
    const response = await fetch(withWorkspace("/graph/actions/generate-edges"), { method: "POST" });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      const detail = payload && payload.detail ? payload.detail : `Edge generation failed: ${response.status}`;
      throw new Error(detail);
    }
    await loadGraph();
  } catch (error) {
    emptyState.classList.remove("hidden");
    nodeDetail.classList.add("hidden");
    emptyState.textContent = error.message;
    setButtonsDisabled(false);
  }
}

function getNodeById(nodeId) {
  return currentData.nodes.find((node) => node.id === nodeId) || null;
}

function toggleDeveloperMode() {
  developerMode = !developerMode;
  window.localStorage.setItem("developerMode", developerMode ? "on" : "off");
  updateDeveloperModeButton();
  const activeNode = getNodeById(activeNodeId);
  if (activeNode) renderDetail(activeNode);
}

function togglePathTracingMode() {
  pathTracingMode = !pathTracingMode;
  if (!pathTracingMode) {
    clearPathTrace();
  } else {
    resetEdgeSelection();
  }
  updatePathTracingButton();
  if (currentData.nodes.length > 0) {
    renderGraph(currentData);
  }
}

function toggleNarrativeMode() {
  narrativeMode = !narrativeMode;
  updateNarrativeModeButton();
}

function zoomIn() {
  setGraphZoom(graphZoom + 0.2);
  renderGraph(currentData);
}

function zoomOut() {
  setGraphZoom(graphZoom - 0.2);
  renderGraph(currentData);
}

function resetZoom() {
  setGraphZoom(1);
  renderGraph(currentData);
}

async function generateNarrativeForNode(nodeId) {
  if (!currentWorkspaceId) return;
  narrativeNodeId = nodeId;
  narrativeLoading = true;
  narrativeText = "";
  narrativeError = "";
  renderGraph(currentData);

  const response = await fetch("/narratives/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workspace_id: currentWorkspaceId,
      root_node_id: nodeId,
      depth: 2,
      max_nodes: 9,
      paragraphs: 2,
    }),
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload && payload.detail ? payload.detail : `Narrative generation failed: ${response.status}`;
    throw new Error(detail);
  }

  const payload = await response.json();
  narrativeNodeId = nodeId;
  narrativeLoading = false;
  narrativeError = "";
  narrativeText = payload.narrative || "";
  renderGraph(currentData);
  const activeNode = getNodeById(nodeId);
  if (activeNode) renderDetail(activeNode);
}

function proposalCard(proposal) {
  const sourceNode = getNodeById(proposal.source_node_id);
  const targetNode = getNodeById(proposal.target_node_id);
  const wrapper = document.createElement("article");
  wrapper.className = "proposal-card";

  const relation = proposal.relation_type.replaceAll("_", " ");
  const confidence = Number(proposal.confidence).toFixed(2);

  wrapper.innerHTML = `
    <div class="proposal-meta">
      <span>${relation}</span>
      <span>confidence ${confidence}</span>
    </div>
    <div class="proposal-body">
      <div class="proposal-node">
        <h4>Source</h4>
        <div>${sourceNode ? sourceNode.raw_text : `Node ${proposal.source_node_id}`}</div>
      </div>
      <div class="proposal-node">
        <h4>Target</h4>
        <div>${targetNode ? targetNode.raw_text : `Node ${proposal.target_node_id}`}</div>
      </div>
      <div class="proposal-node">
        <h4>Why</h4>
        <div>${proposal.evidence || "No evidence recorded."}</div>
      </div>
    </div>
  `;

  const actions = document.createElement("div");
  actions.className = "proposal-actions";

  const discard = document.createElement("button");
  discard.type = "button";
  discard.textContent = "Discard";
  discard.addEventListener("click", async () => {
    try {
      await handleProposalAction(proposal.id, "reject");
    } catch (error) {
      proposalList.innerHTML = `<div class="empty-state">${error.message}</div>`;
    }
  });

  const approve = document.createElement("button");
  approve.type = "button";
  approve.textContent = "Approve";
  approve.addEventListener("click", async () => {
    try {
      await handleProposalAction(proposal.id, "apply");
    } catch (error) {
      proposalList.innerHTML = `<div class="empty-state">${error.message}</div>`;
    }
  });

  actions.appendChild(discard);
  actions.appendChild(approve);
  wrapper.appendChild(actions);
  return wrapper;
}

async function loadProposals() {
  proposalList.innerHTML = "";
  const response = await fetch(withWorkspace("/link-proposals?status_filter=review_needed"));
  if (!response.ok) throw new Error(`Failed to load proposals: ${response.status}`);

  const proposals = await response.json();
  if (proposals.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No proposed links to review.";
    proposalList.appendChild(empty);
    return;
  }

  proposals.forEach((proposal) => {
    proposalList.appendChild(proposalCard(proposal));
  });
}

async function openProposalDrawer() {
  proposalOverlay.classList.remove("hidden");
  proposalList.innerHTML = "";
  try {
    await loadProposals();
  } catch (error) {
    const message = document.createElement("div");
    message.className = "empty-state";
    message.textContent = error.message;
    proposalList.appendChild(message);
  }
}

function closeProposalDrawer() {
  proposalOverlay.classList.add("hidden");
}

async function handleProposalAction(proposalId, action) {
  const response = await fetch(withWorkspace(`/link-proposals/${proposalId}/${action}`), { method: "POST" });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload && payload.detail ? payload.detail : `Proposal action failed: ${response.status}`;
    throw new Error(detail);
  }
  await loadGraph();
  await loadProposals();
}

async function createNodeFromForm(event) {
  event.preventDefault();
  if (!currentWorkspaceId) return;

  const parsed = parseInlineTags(createNodeText.value);
  if (!parsed.rawText) {
    emptyState.classList.remove("hidden");
    nodeDetail.classList.add("hidden");
    emptyState.textContent = "Node text cannot be empty.";
    return;
  }

  const body = {
    workspace_id: currentWorkspaceId,
    type: "idea",
    raw_text: parsed.rawText,
    source: "manual",
    tags: parsed.tags,
  };

  if (currentWorkspaceType === "time_aware") {
    body.time_label = createNodeTime.value.trim();
  }

  setButtonsDisabled(true);
  try {
    const response = await fetch("/nodes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      const detail = payload && payload.detail ? payload.detail : `Create node failed: ${response.status}`;
      throw new Error(detail);
    }
    const createdNode = await response.json();
    createNodeText.value = "";
    createNodeTime.value = "";
    await loadGraph();
    const selectedNode = getNodeById(createdNode.id);
    if (selectedNode) renderDetail(selectedNode);
  } catch (error) {
    emptyState.classList.remove("hidden");
    nodeDetail.classList.add("hidden");
    emptyState.textContent = error.message;
  } finally {
    setButtonsDisabled(false);
  }
}

async function createEdgeFromForm(event) {
  event.preventDefault();
  if (!currentWorkspaceId || !edgeSourceNodeId || !edgeTargetNodeId) {
    emptyState.classList.remove("hidden");
    nodeDetail.classList.add("hidden");
    emptyState.textContent = "Select two nodes before creating an edge.";
    return;
  }

  const weight = Number(createEdgeWeight.value);
  const w = Number.isFinite(weight) ? weight / 100 : 0.1;
  const body = {
    workspace_id: currentWorkspaceId,
    from_node_id: edgeSourceNodeId,
    to_node_id: edgeTargetNodeId,
    type: createEdgeType.value,
    weight: w,
    confidence: w,
    created_by: "manual_ui",
  };

  setButtonsDisabled(true);
  try {
    const response = await fetch("/edges", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      const detail = payload && payload.detail ? payload.detail : `Create edge failed: ${response.status}`;
      throw new Error(detail);
    }
    createEdgeType.value = "related-somehow";
    createEdgeWeight.value = "10";
    edgeWeightDisplay.textContent = "10";
    resetEdgeSelection();
    await loadGraph();
  } catch (error) {
    emptyState.classList.remove("hidden");
    nodeDetail.classList.add("hidden");
    emptyState.textContent = error.message;
  } finally {
    setButtonsDisabled(false);
  }
}

async function saveNodeEdits(nodeId) {
  const newText = detailRaw.value.trim();
  if (!newText) return;

  const tags = Array.from(detailTags.querySelectorAll(".tag[data-tag]")).map((el) => el.dataset.tag);
  const body = { raw_text: newText, tags };

  detailSaveButton.disabled = true;
  try {
    const response = await fetch(withWorkspace(`/nodes/${nodeId}`), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      throw new Error(payload?.detail || `Save failed: ${response.status}`);
    }
    await loadGraph();
    const updated = getNodeById(nodeId);
    if (updated) renderDetail(updated);
  } catch (error) {
    emptyState.classList.remove("hidden");
    nodeDetail.classList.add("hidden");
    emptyState.textContent = error.message;
  } finally {
    detailSaveButton.disabled = false;
  }
}

pollTelegramButton.addEventListener("click", pollTelegram);
generateEdgesButton.addEventListener("click", generateEdges);
graphCanvas.addEventListener("mousemove", (e) => {
  if (!dragNodeId) return;
  const rect = graphCanvas.getBoundingClientRect();
  const svgX = (e.clientX - rect.left - panX) / graphZoom;
  const svgY = (e.clientY - rect.top - panY) / graphZoom;
  const newX = svgX - dragOffsetX;
  const newY = svgY - dragOffsetY;
  if (!dragHasMoved) {
    const old = nodePositions.get(dragNodeId) || { x: 0, y: 0 };
    if (Math.hypot(newX - old.x, newY - old.y) > 4) dragHasMoved = true;
  }
  if (dragHasMoved) {
    graphCanvas.style.cursor = "grabbing";
    applyDragPosition(dragNodeId, newX, newY);
  }
});
document.addEventListener("mouseup", () => {
  if (dragNodeId && dragHasMoved) {
    justDragged = true;
    graphCanvas.style.cursor = "";
    const pos = nodePositions.get(dragNodeId);
    if (pos) saveNodePosition(dragNodeId, pos.x, pos.y);
    renderGraph(currentData);
  }
  dragNodeId = null;
  dragHasMoved = false;
});
graphCanvas.addEventListener("wheel", (e) => {
  e.preventDefault();
  const rect = graphCanvas.getBoundingClientRect();
  const cursorX = e.clientX - rect.left;
  const cursorY = e.clientY - rect.top;

  if (e.ctrlKey) {
    const delta = -e.deltaY * 0.01;
    const newZoom = clampZoom(graphZoom + delta);
    if (newZoom === graphZoom) return;
    panX = cursorX - (cursorX - panX) * (newZoom / graphZoom);
    panY = cursorY - (cursorY - panY) * (newZoom / graphZoom);
    setGraphZoom(newZoom);
  } else {
    panX -= e.deltaX;
    panY -= e.deltaY;
  }

  svg.style.transform = `translate(${panX}px, ${panY}px) scale(${graphZoom})`;
}, { passive: false });
narrativeModeButton.addEventListener("click", toggleNarrativeMode);
pathTracingButton.addEventListener("click", togglePathTracingMode);
toggleAddNodeButton.addEventListener("click", () => {
  addNodeSheet.classList.toggle("hidden");
});
reviewLinksButton.addEventListener("click", openProposalDrawer);
exportGraphButton.addEventListener("click", async () => {
  const parts = ["graph-data/export"];
  const qs = [];
  if (authToken) qs.push(`token=${encodeURIComponent(authToken)}`);
  if (currentWorkspaceId) qs.push(`workspace_id=${encodeURIComponent(String(currentWorkspaceId))}`);
  if (qs.length) parts.push(qs.join("&"));
  const resp = await fetch(`/${parts[0]}?${parts[1] || ""}`);
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const name = (currentWorkspaceName || "graph").toLowerCase().replace(/\s+/g, "-");
  a.download = `seldon-${name}.json`;
  a.click();
  URL.revokeObjectURL(url);
});
developerModeButton.addEventListener("click", toggleDeveloperMode);
themeToggleButton.addEventListener("click", toggleTheme);
workspaceSelect.addEventListener("change", () => {
  graphNeedsCenter = true;
  handleWorkspaceChange().catch((error) => {
    emptyState.classList.remove("hidden");
    nodeDetail.classList.add("hidden");
    emptyState.textContent = error.message;
  });
});
createNodeForm.addEventListener("submit", createNodeFromForm);
createEdgeForm.addEventListener("submit", createEdgeFromForm);
createEdgeWeight.addEventListener("input", () => { edgeWeightDisplay.textContent = createEdgeWeight.value; });
closeProposalsButton.addEventListener("click", closeProposalDrawer);
detailSaveButton.addEventListener("click", () => { if (activeNodeId) saveNodeEdits(activeNodeId); });
detailRaw.addEventListener("input", () => {
  detailRaw.style.height = "auto";
  detailRaw.style.height = `${detailRaw.scrollHeight}px`;
});
detailTagInput.addEventListener("keydown", (e) => {
  if (e.key !== "Enter") return;
  e.preventDefault();
  const value = detailTagInput.value.trim().toLowerCase().replace(/^#/, "");
  if (!value) return;
  if (detailTags.querySelector(`[data-tag="${value}"]`)) { detailTagInput.value = ""; return; }
  detailTags.appendChild(makeEditableTag(value));
  detailTagInput.value = "";
});
proposalOverlay.addEventListener("click", (event) => {
  if (event.target === proposalOverlay) closeProposalDrawer();
});
window.addEventListener("resize", () => renderGraph(currentData));
window.addEventListener("DOMContentLoaded", () => {
  applyTheme();
  updateDeveloperModeButton();
  updateNarrativeModeButton();
  updatePathTracingButton();
  waitForSetup();
  document.getElementById("logout-button").addEventListener("click", () => {
    window.localStorage.removeItem("authToken");
    window.localStorage.removeItem("workspaceId");
    window.location.href = "/login";
  });
});
async function handleWorkspaceChange() {
  const nextWorkspaceId = Number(workspaceSelect.value);
  if (!nextWorkspaceId || nextWorkspaceId === currentWorkspaceId) return;

  const switchBody = authToken
    ? { workspace_name: workspaceSelect.options[workspaceSelect.selectedIndex].textContent }
    : { workspace_id: nextWorkspaceId };
  const response = await fetch(withToken("/workspaces/switch"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(switchBody),
  });
  if (!response.ok) {
    throw new Error(`Workspace switch failed: ${response.status}`);
  }

  const payload = await response.json();
  currentWorkspaceId = payload.id;
  currentWorkspaceName = payload.display_name || payload.name;
  currentWorkspaceType = payload.type;
  window.localStorage.setItem("workspaceId", String(currentWorkspaceId));
  nodePositions.clear();
  resetEdgeSelection();
  narrativeNodeId = null;
  narrativeText = "";
  narrativeError = "";
  narrativeLoading = false;
  clearPathTrace();
  await loadWorkspaces();
  await loadGraph();
}
