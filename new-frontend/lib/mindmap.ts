import type { Edge, Node } from "@xyflow/react";
import type { MindMapNode } from "@/lib/schemas";

export type ExpandedMap = Record<string, boolean>;

export type MindMapFlowNodeData = {
  node: MindMapNode;
  expanded: boolean;
  hasChildren: boolean;
  onToggle: (nodeId: string) => void;
};

const DEPTH_GAP = 360;
const SIBLING_GAP = 190;

export function createExpandedMap(root: MindMapNode): ExpandedMap {
  const expanded: ExpandedMap = {};
  walkTree(root, (node, depth) => {
    expanded[node.id] = depth === 0;
  });
  return expanded;
}

export function expandAll(root: MindMapNode): ExpandedMap {
  const expanded: ExpandedMap = {};
  walkTree(root, (node) => {
    expanded[node.id] = true;
  });
  return expanded;
}

export function collapseAll(root: MindMapNode): ExpandedMap {
  const expanded: ExpandedMap = {};
  walkTree(root, (node, depth) => {
    expanded[node.id] = depth === 0;
  });
  return expanded;
}

export function toggleNode(expanded: ExpandedMap, nodeId: string): ExpandedMap {
  return {
    ...expanded,
    [nodeId]: !expanded[nodeId]
  };
}

export function buildFlowElements(
  root: MindMapNode,
  expanded: ExpandedMap,
  onToggle: (nodeId: string) => void
): { nodes: Node<MindMapFlowNodeData>[]; edges: Edge[] } {
  const positions = new Map<string, { x: number; y: number }>();
  let leafCursor = 0;

  const rootLeafCenter = computeLayout(root, 0, expanded, positions, () => {
    const next = leafCursor;
    leafCursor += 1;
    return next;
  });

  const yOffset = -(rootLeafCenter * SIBLING_GAP);

  const nodes: Node<MindMapFlowNodeData>[] = [];
  const edges: Edge[] = [];

  const visit = (node: MindMapNode, parentId?: string) => {
    const sourcePosition = positions.get(node.id) ?? { x: 0, y: 0 };
    const hasChildren = node.children.length > 0;

    nodes.push({
      id: node.id,
      type: "mindmapNode",
      position: {
        x: sourcePosition.x,
        y: sourcePosition.y + yOffset
      },
      draggable: true,
      dragHandle: ".mindmap-drag-handle",
      data: {
        node,
        expanded: Boolean(expanded[node.id]),
        hasChildren,
        onToggle
      }
    });

    if (parentId) {
      edges.push({
        id: `${parentId}->${node.id}`,
        source: parentId,
        target: node.id,
        type: "smoothstep",
        selectable: false
      });
    }

    if (!expanded[node.id]) {
      return;
    }

    for (const child of node.children) {
      visit(child, node.id);
    }
  };

  visit(root);

  return { nodes, edges };
}

function walkTree(node: MindMapNode, visit: (node: MindMapNode, depth: number) => void, depth = 0) {
  visit(node, depth);
  for (const child of node.children) {
    walkTree(child, visit, depth + 1);
  }
}

function computeLayout(
  node: MindMapNode,
  depth: number,
  expanded: ExpandedMap,
  positions: Map<string, { x: number; y: number }>,
  nextLeaf: () => number
): number {
  const visibleChildren = expanded[node.id] ? node.children : [];

  if (!visibleChildren.length) {
    const row = nextLeaf();
    positions.set(node.id, {
      x: depth * DEPTH_GAP,
      y: row * SIBLING_GAP
    });
    return row;
  }

  const childRows = visibleChildren.map((child) => computeLayout(child, depth + 1, expanded, positions, nextLeaf));
  const centerRow = (childRows[0] + childRows[childRows.length - 1]) / 2;

  positions.set(node.id, {
    x: depth * DEPTH_GAP,
    y: centerRow * SIBLING_GAP
  });

  return centerRow;
}
