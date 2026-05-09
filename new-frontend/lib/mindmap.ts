import { Position, type Edge, type Node } from "@xyflow/react";
import type { MindMapNode } from "@/lib/schemas";

type VisibilityMap = Record<string, boolean>;

const NODE_WIDTH = 280;
const NODE_HEIGHT = 172;
const X_SPACING = 360;
const Y_SPACING = 52;

export function createExpandedMap(root: MindMapNode, initialDepth = 0) {
  const expanded: VisibilityMap = {};

  function visit(node: MindMapNode, depth: number) {
    expanded[node.id] = depth < initialDepth;
    for (const child of node.children) {
      visit(child, depth + 1);
    }
  }

  visit(root, 0);
  expanded[root.id] = true;
  return expanded;
}

export function expandAll(root: MindMapNode) {
  return createExpandedMap(root, Number.POSITIVE_INFINITY);
}

export function collapseAll(root: MindMapNode) {
  return createExpandedMap(root, 0);
}

export function toggleNode(expanded: VisibilityMap, nodeId: string) {
  return {
    ...expanded,
    [nodeId]: !expanded[nodeId]
  };
}

export function buildFlowElements(
  root: MindMapNode,
  expanded: VisibilityMap,
  onToggle: (nodeId: string) => void
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  const measurements = new Map<string, number>();

  function measure(node: MindMapNode): number {
    if (measurements.has(node.id)) {
      return measurements.get(node.id)!;
    }

    const visibleChildren = expanded[node.id] ? node.children : [];
    if (!visibleChildren.length) {
      measurements.set(node.id, NODE_HEIGHT);
      return NODE_HEIGHT;
    }

    const childrenHeight =
      visibleChildren.reduce((total, child) => total + measure(child), 0) + Y_SPACING * (visibleChildren.length - 1);
    const height = Math.max(NODE_HEIGHT, childrenHeight);
    measurements.set(node.id, height);
    return height;
  }

  function layout(node: MindMapNode, depth: number, top: number, parentId?: string) {
    const subtreeHeight = measure(node);
    const visibleChildren = expanded[node.id] ? node.children : [];
    const childrenHeight = visibleChildren.length
      ? visibleChildren.reduce((total, child) => total + measure(child), 0) + Y_SPACING * (visibleChildren.length - 1)
      : 0;
    const centeredTop = top + (subtreeHeight - NODE_HEIGHT) / 2;

    nodes.push({
      id: node.id,
      position: {
        x: depth * X_SPACING,
        y: centeredTop
      },
      type: "mindmapNode",
      data: {
        node,
        expanded: expanded[node.id],
        hasChildren: node.children.length > 0,
        onToggle
      },
      width: NODE_WIDTH,
      draggable: true,
      dragHandle: ".mindmap-drag-handle",
      sourcePosition: Position.Right,
      targetPosition: Position.Left
    });

    if (parentId) {
      edges.push({
        id: `${parentId}-${node.id}`,
        source: parentId,
        target: node.id,
        type: "smoothstep",
        animated: false
      });
    }

    if (!visibleChildren.length) {
      return;
    }

    let childTop = top + (subtreeHeight - childrenHeight) / 2;
    for (const child of visibleChildren) {
      const childHeight = measure(child);
      layout(child, depth + 1, childTop, node.id);
      childTop += childHeight + Y_SPACING;
    }
  }

  layout(root, 0, 0);

  return { nodes, edges };
}
