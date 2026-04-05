const svg = document.getElementById("embed-graph-svg");
const graphCanvas = document.getElementById("embed-graph-canvas");
const emptyState = document.getElementById("embed-empty-state");
const nodeDetail = document.getElementById("embed-node-detail");
const workspaceName = document.getElementById("embed-workspace-name");
const detailRaw = document.getElementById("embed-detail-raw");
const detailTags = document.getElementById("embed-detail-tags");

let currentData = { nodes: [], edges: [], workspace: null };
let activeNodeId = null;

function getParams() {
  const params = new URLSearchParams(window.location.search);
  return {
    workspaceId: params.get("workspace_id"),
    token: params.get("token"),
  };
}

function clearSvg() {
  while (svg.firstChild) svg.removeChild(svg.firstChild);
}

function svgEl(name, attrs = {}) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attrs).forEach(([key, value]) => element.setAttribute(key, String(value)));
  return element;
}

function polarLayout(nodes, width, height) {
  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.max(Math.min(width, height) * 0.32, 120);
  return nodes.map((node, index) => {
    const angle = (index / Math.max(nodes.length, 1)) * Math.PI * 2;
    const orbital = radius + (index % 5) * 28;
    return {
      ...node,
      x: centerX + Math.cos(angle) * orbital,
      y: centerY + Math.sin(angle) * orbital,
    };
  });
}

function wrapText(text, maxCharsPerLine = 22, maxLines = 5) {
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
    if (lines.length === maxLines - 1) break;
  }
  if (current && lines.length < maxLines) lines.push(current);
  if (lines.length === maxLines && words.join(" ").length > lines.join(" ").length) {
    lines[maxLines - 1] = `${lines[maxLines - 1].replace(/[.,;:!?]?$/, "")}...`;
  }
  return lines.slice(0, maxLines);
}

function getNoteSize(node) {
  const length = (node.raw_text || node.label || "").length;
  const width = length > 240 ? 206 : 178;
  const lines = wrapText(node.label || node.raw_text || "");
  const minHeight = 86;
  const bodyHeight = 26 + lines.length * 20;
  const extra = length > 240 ? 26 : length > 140 ? 12 : 0;
  return { width, height: Math.max(minHeight, bodyHeight + extra), lines };
}

function buildSlackPath(from, to) {
  const dx = to.x - from.x;
  const distance = Math.hypot(dx, to.y - from.y);
  const sag = Math.max(20, Math.min(54, distance * 0.15));
  return `M ${from.x} ${from.y} C ${from.x + dx * 0.3} ${from.y + sag}, ${from.x + dx * 0.7} ${to.y + sag}, ${to.x} ${to.y}`;
}

function renderTags(tags) {
  detailTags.innerHTML = "";
  if (!tags || tags.length === 0) {
    const tag = document.createElement("span");
    tag.className = "embed-tag";
    tag.textContent = "untagged";
    detailTags.appendChild(tag);
    return;
  }
  tags.forEach((value) => {
    const tag = document.createElement("span");
    tag.className = "embed-tag";
    tag.textContent = value;
    detailTags.appendChild(tag);
  });
}

function renderDetail(node) {
  activeNodeId = node.id;
  emptyState.classList.add("hidden");
  nodeDetail.classList.remove("hidden");
  workspaceName.textContent = currentData.workspace ? currentData.workspace.name : "Embedded Graph";
  detailRaw.textContent = node.raw_text;
  renderTags(node.tags || []);

  document.querySelectorAll(".embed-node-card").forEach((card) => {
    card.classList.toggle("is-active", Number(card.dataset.nodeId) === node.id);
  });
}

function renderGraph(data) {
  currentData = data;
  clearSvg();
  const width = graphCanvas.clientWidth;
  const height = graphCanvas.clientHeight;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);

  const layoutNodes = polarLayout(data.nodes, width, height);
  const nodeMap = new Map(layoutNodes.map((node) => [node.id, node]));

  data.edges.forEach((edge) => {
    const from = nodeMap.get(edge.from_node_id);
    const to = nodeMap.get(edge.to_node_id);
    if (!from || !to) return;
    const path = svgEl("path", {
      d: buildSlackPath(from, to),
      class: "embed-edge",
      "stroke-width": Math.max(1.2, edge.weight * 2.6),
    });
    svg.appendChild(path);

    const label = svgEl("text", {
      x: (from.x + to.x) / 2,
      y: (from.y + to.y) / 2 + 12,
      class: "embed-edge-label",
      "text-anchor": "middle",
    });
    label.textContent = edge.type.replaceAll("_", " ");
    svg.appendChild(label);
  });

  layoutNodes.forEach((node) => {
    const group = svgEl("g", { transform: `translate(${node.x} ${node.y})`, style: "cursor:pointer" });
    const size = getNoteSize(node);

    const base = svgEl("rect", {
      x: -size.width / 2,
      y: -size.height / 2,
      width: size.width,
      height: size.height,
      rx: 8,
      ry: 8,
      class: "embed-node-card",
      "data-node-id": node.id,
    });
    if (activeNodeId === node.id) base.classList.add("is-active");
    group.appendChild(base);

    if (node.type === "topic") {
      const stamp = svgEl("text", {
        x: -size.width / 2 + 14,
        y: -size.height / 2 + 16,
        class: "embed-topic-stamp",
      });
      stamp.textContent = "TOPIC";
      group.appendChild(stamp);
    }

    const label = svgEl("text", {
      x: -size.width / 2 + 14,
      y: -size.height / 2 + 24,
      class: "embed-node-label",
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
    group.addEventListener("click", () => renderDetail(node));
    svg.appendChild(group);
  });

  if (!activeNodeId && layoutNodes.length > 0) {
    renderDetail(layoutNodes[0]);
  }
}

async function loadEmbed() {
  const { workspaceId, token } = getParams();
  if (!workspaceId || !token) {
    emptyState.textContent = "workspace_id and token are required.";
    return;
  }

  const response = await fetch(`/embed/graph-data?workspace_id=${encodeURIComponent(workspaceId)}&token=${encodeURIComponent(token)}`);
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    emptyState.textContent = payload && payload.detail ? payload.detail : `Embed failed: ${response.status}`;
    return;
  }
  const data = await response.json();
  renderGraph(data);
}

window.addEventListener("resize", () => renderGraph(currentData));
window.addEventListener("DOMContentLoaded", () => {
  loadEmbed().catch((error) => {
    emptyState.textContent = error.message;
  });
});
