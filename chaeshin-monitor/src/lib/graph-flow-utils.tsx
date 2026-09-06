"use client";

/**
 * React Flow ↔ Chaeshin ToolGraph 변환 유틸 + 커스텀 노드.
 * ToolGraphEditor와 GraphBuilder 페이지에서 공유.
 */

import {
  Handle,
  Position,
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type Node,
  type Edge,
  type EdgeProps,
  type NodeTypes,
  type EdgeTypes,
} from "@xyflow/react";
import type {
  ChaeshinToolGraph,
  ChaeshinGraphNode,
  ChaeshinGraphEdge,
} from "./chaeshin-types";

// ── 커스텀 노드 ──────────────────────────────────────────────

/** 도구 id·이름·설명을 표시하고 entry 여부를 테두리로 구분하는 Flow 노드. */
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

/** 실제 Tool Graph 노드는 아니지만 종료 action을 연결 대상으로 보여주는 합성 노드. */
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

// ── 삭제 가능한 커스텀 엣지 ──────────────────────────────────

/** 엣지 조건과 hover 삭제 버튼을 베지어 경로 중앙에 함께 렌더링한다. */
export function DeletableEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style,
  markerEnd,
  label,
  data,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const onDelete = data?.onDelete as ((id: string) => void) | undefined;

  return (
    <>
      <BaseEdge path={edgePath} markerEnd={markerEnd} style={style} />
      <EdgeLabelRenderer>
        <div
          style={{
            position: "absolute",
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: "all",
          }}
          className="nodrag nopan group"
        >
          {label && (
            <span className="text-[10px] bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded border border-amber-200">
              {String(label)}
            </span>
          )}
          {onDelete && (
            <button
              onClick={() => onDelete(id)}
              className="absolute -top-2 -right-2 w-4 h-4 rounded-full bg-red-500 text-white text-[9px] leading-none flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-600 shadow-sm"
              title="엣지 삭제"
            >
              ×
            </button>
          )}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

export const edgeTypes: EdgeTypes = {
  deletable: DeletableEdge,
};

// ── Tool Graph → React Flow ──────────────────────────────────

/**
 * 도메인 Tool Graph를 화면용 Flow 노드·엣지로 변환한다.
 * 저장 좌표가 없는 도메인 노드는 고정 격자에 배치하고 action edge는 합성 노드로 확장한다.
 */
export function graphToFlow(graph: ChaeshinToolGraph, onDeleteEdge?: (id: string) => void): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  const actionNodes = new Set<string>();

  // 재현 가능한 초기 배치를 위해 입력 순서대로 3열 격자를 사용한다.
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
        type: onDeleteEdge ? "deletable" : undefined,
        label: e.condition || undefined,
        animated: !!e.condition,
        style: { stroke: e.condition ? "#f59e0b" : "#94a3b8" },
        data: onDeleteEdge ? { onDelete: onDeleteEdge } : undefined,
      });
    } else if (e.action) {
      // action은 도메인 edge 속성이므로 Flow에서 연결할 임시 target 노드가 필요하다.
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
        type: onDeleteEdge ? "deletable" : undefined,
        label: e.condition || undefined,
        animated: true,
        style: { stroke: "#ef4444" },
        data: onDeleteEdge ? { onDelete: onDeleteEdge } : undefined,
      });
    }
  });

  return { nodes, edges };
}

// ── React Flow → Tool Graph ──────────────────────────────────

/**
 * 편집된 Flow 구조를 Tool Graph로 되돌린다.
 * 화면 전용 action 노드는 edge.action으로 접고 원본의 schema·병렬 설정·loop 제한은 보존한다.
 */
export function flowToGraph(
  nodes: Node[],
  edges: Edge[],
  originalGraph: ChaeshinToolGraph
): ChaeshinToolGraph {
  // 합성 action 노드는 제외하고 원본 노드의 실행 hint/schema를 id 기준으로 복원한다.
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

  // action target은 실제 to_node가 아니므로 target data를 다시 action 필드로 접는다.
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

  // 들어오는 일반 엣지가 없는 도구를 entry로 재계산하되 모두 순환이면 원본을 유지한다.
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
