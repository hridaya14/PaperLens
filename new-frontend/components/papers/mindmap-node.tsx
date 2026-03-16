"use client";

import type { NodeProps } from "@xyflow/react";
import { Handle, Position } from "@xyflow/react";
import { ChevronRight, Dot, GripHorizontal } from "lucide-react";
import type { MindMapNode } from "@/lib/schemas";
import { cn } from "@/lib/utils";

const NODE_STYLES: Record<MindMapNode["node_type"], string> = {
  root: "border-amber-400/30 bg-gradient-to-br from-amber-300/25 to-orange-500/15 text-amber-50",
  problem: "border-rose-400/30 bg-gradient-to-br from-rose-400/20 to-transparent text-rose-50",
  approach: "border-sky-400/30 bg-gradient-to-br from-sky-400/20 to-transparent text-sky-50",
  concept: "border-cyan-400/30 bg-gradient-to-br from-cyan-400/18 to-transparent text-cyan-50",
  finding: "border-emerald-400/30 bg-gradient-to-br from-emerald-400/18 to-transparent text-emerald-50",
  limitation: "border-fuchsia-400/30 bg-gradient-to-br from-fuchsia-400/18 to-transparent text-fuchsia-50",
  contribution: "border-orange-400/30 bg-gradient-to-br from-orange-400/18 to-transparent text-orange-50"
};

type MindMapNodeData = {
  node: MindMapNode;
  expanded: boolean;
  hasChildren: boolean;
  onToggle: (nodeId: string) => void;
};

export function MindMapFlowNode({ data }: NodeProps) {
  const payload = data as MindMapNodeData;
  const node = payload.node;

  return (
    <div
      className={cn(
        "w-[280px] rounded-[26px] border px-5 py-5 text-left shadow-[0_28px_60px_rgba(0,0,0,0.25)] backdrop-blur",
        NODE_STYLES[node.node_type]
      )}
    >
      <Handle type="target" position={Position.Left} className="!h-2.5 !w-2.5 !border-0 !bg-white/22" />
      <div className="mb-4 flex items-start justify-between gap-4">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-[0.2em] text-white/58">{node.node_type}</span>
            {payload.hasChildren ? (
              <ChevronRight className={cn("h-4 w-4 text-white/50 transition-transform", payload.expanded && "rotate-90")} />
            ) : (
              <Dot className="h-4 w-4 text-white/40" />
            )}
          </div>
          <p className="pr-4 text-base font-semibold leading-6 text-white">{node.label}</p>
        </div>
        <div className="mindmap-drag-handle inline-flex cursor-grab items-center rounded-full border border-white/12 bg-black/10 px-2 py-1 text-white/55 active:cursor-grabbing">
          <GripHorizontal className="h-4 w-4" />
        </div>
      </div>

      {node.description ? <p className="text-xs leading-6 text-white/70">{node.description}</p> : null}
      {node.source_section ? (
        <div className="mt-4 inline-flex rounded-full border border-white/10 bg-white/10 px-2 py-1 text-[10px] uppercase tracking-[0.18em] text-white/70">
          {node.source_section}
        </div>
      ) : null}
      {payload.hasChildren ? (
        <button
          type="button"
          onClick={() => payload.onToggle(node.id)}
          className="mt-4 inline-flex items-center gap-2 rounded-full border border-white/10 bg-black/10 px-3 py-2 text-xs font-medium uppercase tracking-[0.18em] text-white/72 transition hover:bg-white/10"
        >
          {payload.expanded ? "Collapse" : "Expand"}
          <ChevronRight className={cn("h-3.5 w-3.5 transition-transform", payload.expanded && "rotate-90")} />
        </button>
      ) : null}
      <Handle type="source" position={Position.Right} className="!h-2.5 !w-2.5 !border-0 !bg-white/22" />
    </div>
  );
}
