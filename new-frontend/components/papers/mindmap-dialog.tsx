"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
} from "@xyflow/react";
import { BrainCircuit, Move, RefreshCw, Shrink, Sparkles } from "lucide-react";
import type { Paper } from "@/lib/schemas";
import { getMindMap } from "@/lib/api/client";
import {
  buildFlowElements,
  collapseAll,
  createExpandedMap,
  expandAll,
  toggleNode,
} from "@/lib/mindmap";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { MindMapFlowNode } from "@/components/papers/mindmap-node";

type MindMapDialogProps = {
  paper: Paper | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

const nodeTypes = {
  mindmapNode: MindMapFlowNode,
};

export function MindMapDialog({
  paper,
  open,
  onOpenChange,
}: MindMapDialogProps) {
  const paperRef = paper?.arxiv_id ?? paper?.id ?? null;
  const mindMapQuery = useQuery({
    queryKey: ["mindmap", paperRef],
    queryFn: () => {
      if (!paperRef) {
        return Promise.reject(new Error("Missing paper reference"));
      }
      return getMindMap(paperRef);
    },
    enabled: open && Boolean(paperRef),
  });

  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  useEffect(() => {
    if (mindMapQuery.data) {
      setExpanded(createExpandedMap(mindMapQuery.data.root));
    }
  }, [mindMapQuery.data]);

  useEffect(() => {
    if (!mindMapQuery.data) {
      setNodes([]);
      setEdges([]);
      return;
    }

    const flow = buildFlowElements(mindMapQuery.data.root, expanded, (nodeId) =>
      setExpanded((current) => toggleNode(current, nodeId)),
    );

    setNodes(flow.nodes);
    setEdges(flow.edges);
  }, [expanded, mindMapQuery.data, setEdges, setNodes]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="panel-dark h-[92vh] max-w-[94vw] overflow-hidden border-white/10 bg-graphite-900 p-0">
        <DialogHeader className="border-b border-white/10 px-8 py-6">
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <div className="eyebrow border-white/10 bg-white/5 text-paper-100">
              Knowledge map
            </div>
            {mindMapQuery.data ? (
              <div className="text-xs uppercase tracking-[0.2em] text-white/40">
                Model {mindMapQuery.data.model_used}
              </div>
            ) : null}
          </div>
          <DialogTitle className="text-white">
            {paper?.title ?? "Mind Map"}
          </DialogTitle>
          <DialogDescription className="max-w-3xl text-white/65">
            Explore the paper as a collapsible concept tree. Click any node to
            expand or collapse its local branch.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-1 flex-col overflow-hidden lg:flex-row">
          <div className="flex w-full flex-col border-b border-white/10 lg:w-[320px] lg:border-b-0 lg:border-r">
            <ScrollArea className="h-full">
              <div className="space-y-5 p-6 text-sm text-white/75">
                <div className="rounded-[24px] border border-white/10 bg-white/5 p-5">
                  <div className="mb-3 flex items-center gap-2 text-white">
                    <BrainCircuit className="h-4 w-4" />
                    Mind map controls
                  </div>
                  <div className="grid gap-3">
                    <Button
                      variant="secondary"
                      onClick={() =>
                        mindMapQuery.data &&
                        setExpanded(expandAll(mindMapQuery.data.root))
                      }
                    >
                      <Sparkles className="h-4 w-4" />
                      Expand all
                    </Button>
                    <Button
                      variant="outline"
                      className="border-white/15 bg-white/5 text-white hover:bg-white/10"
                      onClick={() =>
                        mindMapQuery.data &&
                        setExpanded(collapseAll(mindMapQuery.data.root))
                      }
                    >
                      <Shrink className="h-4 w-4" />
                      Collapse all
                    </Button>
                    <Button
                      variant="outline"
                      className="border-white/15 bg-white/5 text-white hover:bg-white/10"
                      onClick={() => mindMapQuery.refetch()}
                    >
                      <RefreshCw className="h-4 w-4" />
                      Refresh
                    </Button>
                  </div>
                </div>

                <div className="rounded-[24px] border border-white/10 bg-white/5 p-5 text-xs leading-6 text-white/58">
                  <div className="mb-2 flex items-center gap-2 text-white/76">
                    <Move className="h-4 w-4" />
                    Layout tips
                  </div>
                  Use the grip pill on each node to drag it into a clearer
                  working position. The built-in controls also let you zoom and
                  refit the canvas.
                </div>

                {mindMapQuery.data?.sections_covered.length ? (
                  <div className="rounded-[24px] border border-white/10 bg-white/5 p-5">
                    <p className="mb-3 text-xs uppercase tracking-[0.22em] text-white/45">
                      Sections covered
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {mindMapQuery.data.sections_covered.map((section) => (
                        <span
                          key={section}
                          className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-white/70"
                        >
                          {section}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}

                <div className="rounded-[24px] border border-white/10 bg-white/5 p-5 text-xs leading-6 text-white/58">
                  The backend generates this structure on demand from indexed
                  paper chunks and caches it for faster revisits.
                </div>
              </div>
            </ScrollArea>
          </div>

          <div className="relative min-h-[560px] flex-1">
            {mindMapQuery.isLoading ? (
              <div className="flex h-full items-center justify-center text-sm text-white/65">
                Generating mind map. First load can take a little while.
              </div>
            ) : mindMapQuery.isError ? (
              <div className="flex h-full items-center justify-center px-8 text-center text-sm text-rose-200">
                {mindMapQuery.error instanceof Error
                  ? mindMapQuery.error.message
                  : "Unable to generate mind map."}
              </div>
            ) : mindMapQuery.data ? (
              <ReactFlowProvider>
                <ReactFlow
                  nodes={nodes}
                  edges={edges}
                  nodeTypes={nodeTypes}
                  onNodesChange={onNodesChange}
                  onEdgesChange={onEdgesChange}
                  fitView
                  fitViewOptions={{ padding: 0.28 }}
                  minZoom={0.16}
                  maxZoom={1.8}
                  snapToGrid
                  snapGrid={[24, 24]}
                  defaultEdgeOptions={{
                    style: {
                      stroke: "rgba(255,255,255,0.16)",
                      strokeWidth: 1.6,
                    },
                  }}
                  className="bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.06),transparent_45%),linear-gradient(180deg,rgba(8,12,12,0.28),rgba(8,12,12,0.12))]"
                >
                  <Background
                    gap={28}
                    size={1}
                    color="rgba(255,255,255,0.06)"
                  />
                  <MiniMap
                    pannable
                    zoomable
                    nodeColor="rgba(255,255,255,0.45)"
                    maskColor="rgba(8,12,12,0.45)"
                    className="!rounded-2xl !border !border-white/10 !bg-black/30"
                  />
                  <Controls className="[&_button]:!border-white/10 [&_button]:!bg-white/10 [&_button]:!text-white [&_button:hover]:!bg-white/15" />
                </ReactFlow>
              </ReactFlowProvider>
            ) : null}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
