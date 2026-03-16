import { describe, expect, it, vi } from "vitest";
import { buildFlowElements, collapseAll, createExpandedMap, expandAll, toggleNode } from "@/lib/mindmap";
import type { MindMapNode } from "@/lib/schemas";

const tree: MindMapNode = {
  id: "root",
  label: "Root",
  node_type: "root",
  importance: "primary",
  children: [
    {
      id: "child-1",
      label: "Child One",
      node_type: "concept",
      importance: "primary",
      children: []
    },
    {
      id: "child-2",
      label: "Child Two",
      node_type: "approach",
      importance: "secondary",
      children: [
        {
          id: "grandchild",
          label: "Grandchild",
          node_type: "finding",
          importance: "tertiary",
          children: []
        }
      ]
    }
  ]
};

describe("mindmap helpers", () => {
  it("creates the initial expanded state up to depth 1", () => {
    const expanded = createExpandedMap(tree);
    expect(expanded.root).toBe(true);
    expect(expanded["child-1"]).toBe(false);
    expect(expanded["grandchild"]).toBe(false);
  });

  it("supports expand all, collapse all, and toggling nodes", () => {
    expect(expandAll(tree)["grandchild"]).toBe(true);
    expect(collapseAll(tree)["child-1"]).toBe(false);
    expect(toggleNode({ root: true }, "root").root).toBe(false);
  });

  it("builds flow nodes and edges for visible branches", () => {
    const expanded = createExpandedMap(tree);
    const flow = buildFlowElements(tree, expanded, vi.fn());

    expect(flow.nodes.map((node) => node.id)).toEqual(["root", "child-1", "child-2"]);
    expect(flow.edges).toHaveLength(2);
  });
});
