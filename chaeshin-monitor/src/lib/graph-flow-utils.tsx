"use client";

/**
 * React Flow ↔ Chaeshin ToolGraph 변환 유틸 + 커스텀 노드.
 * ToolGraphEditor와 GraphBuilder 페이지에서 공유.
 */

import { Handle, Position, type Node, type Edge, type NodeTypes } from "@xyflow/react";
import type {
  ChaeshinToolGraph,
  ChaeshinGraphNode,
  ChaeshinGraphEdge,
} from "./chaeshin-types";

// ── Custom Nodes ─────────────────────────────────────────────

export function ToolNode({ data }: { data: { label: string; tool: string; note: string; isEntry: boolean } }) {
  return (
    <div
      className={`px-3 py-2 rounded-lg border-2 shadow-sm min-w-[140px] ${
        data.isEntry
          ? "border-green-500 bg-green-50"
          : "border-gray-300 bg-white"
      }`}
    >
      <Handle type="target" position={Position.Top} className="!bg-gray-400 !w-2 !h-2" />
      <div className="text-xs font-mono text-muted-foreground">{data.label}</div>
      <div className="text-sm font-semibold">{data.tool}</div>
      {data.note && <div className="text-xs text-muted-foreground mt-0.5">{data.note}</div>}
      <Handle type="source" position={Position.Bottom} className="!bg-gray-400 !w-2 !h-2" />
    </div>
  );
}

export function ActionNode({ data }: { data: { action: string } }) {
  return (
    <div className="px-3 py-2 rounded-full border-2 border-red-400 bg-red-50 text-center min-w-[80px]">
      <Handle type="target" position={Position.Top} className="!bg-red-400 !w-2 !h-2" />
      <div className="text-xs font-semibold text-red-700">{data.action}</div>
    </div>
  );
}

export const nodeTypes: NodeTypes = {
  tool: ToolNode,
  action: ActionNode,
};

// ── Graph → React Flow ───────────────────────────────────────

export function graphToFlow(graph: ChaeshinToolGraph): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  const actionNodes = new Set<string>();

  graph.nodes.forEach((n, i) => {
    const col = i % 3;
    const row = Math.floor(i / 3);
    nodes.push({
      id: n.id,
      type: "tool",
      position: { x: 50 + col * 220, y: 50 + row * 140 },
      data: {
        label: n.id,
        tool: n.tool,
        note: n.note,
        isEntry: graph.entry_nodes.includes(n.id),
      },
    });
  });

  graph.edges.forEach((e, i) => {
    if (e.to_node) {
      edges.push({
        id: `e-${i}`,
        source: e.from_node,
        target: e.to_node,
        label: e.condition || undefined,
        animated: !!e.condition,
        style: { stroke: e.condition ? "#f59e0b" : "#94a3b8" },
      });
    } else if (e.action) {
      const actionId = `action-${e.action}-${e.from_node}`;
      if (!actionNodes.has(actionId)) {
        actionNodes.add(actionId);
        const sourceNode = nodes.find((n) => n.id === e.from_node);
        nodes.push({
          id: actionId,
          type: "action",
          position: {
            x: (sourceNode?.position.x ?? 200) + 180,
            y: (sourceNode?.position.y ?? 100),
          },
          data: { action: e.action },
        });
      }
      edges.push({
        id: `e-${i}`,
        source: e.from_node,
        target: actionId,
        label: e.condition || undefined,
        animated: true,
        style: { stroke: "#ef4444" },
      });
    }
  });

  return { nodes, edges };
}

// ── React Flow → Graph ───────────────────────────────────────

export function flowToGraph(
  nodes: Node[],
  edges: Edge[],
  originalGraph: ChaeshinToolGraph
): ChaeshinToolGraph {
  const toolNodes: ChaeshinGraphNode[] = nodes
    .filter((n) => n.type === "tool")
    .map((n) => {
      const orig = originalGraph.nodes.find((on) => on.id === n.id);
      return {
        id: n.id,
        tool: n.data.tool as string,
        params_hint: orig?.params_hint ?? {},
        note: (n.data.note as string) || "",
        input_schema: orig?.input_schema ?? {},
        output_schema: orig?.output_schema ?? {},
      };
    });

  const graphEdges: ChaeshinGraphEdge[] = edges.map((e) => {
    const isAction = e.target.startsWith("action-");
    return {
      from_node: e.source,
      to_node: isAction ? null : e.target,
      condition: (e.label as string) || null,
      action: isAction ? (nodes.find((n) => n.id === e.target)?.data.action as string) ?? null : null,
      priority: 0,
      note: "",
    };
  });

  const entryNodes = toolNodes
    .filter((n) => !graphEdges.some((e) => e.to_node === n.id))
    .map((n) => n.id);

  return {
    nodes: toolNodes,
    edges: graphEdges,
    parallel_groups: originalGraph.parallel_groups,
    entry_nodes: entryNodes.length > 0 ? entryNodes : originalGraph.entry_nodes,
    max_loops: originalGraph.max_loops,
  };
}
