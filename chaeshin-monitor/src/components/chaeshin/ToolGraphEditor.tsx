"use client";

import { useCallback, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type Connection,
  type NodeTypes,
  Handle,
  Position,
  Panel,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import type {
  ChaeshinToolGraph,
  ChaeshinGraphNode,
  ChaeshinGraphEdge,
} from "@/lib/chaeshin-types";
import { Plus, Save, Trash2 } from "lucide-react";

// ── Custom Node ──────────────────────────────────────────────

function ToolNode({ data }: { data: { label: string; tool: string; note: string; isEntry: boolean } }) {
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

function ActionNode({ data }: { data: { action: string } }) {
  return (
    <div className="px-3 py-2 rounded-full border-2 border-red-400 bg-red-50 text-center min-w-[80px]">
      <Handle type="target" position={Position.Top} className="!bg-red-400 !w-2 !h-2" />
      <div className="text-xs font-semibold text-red-700">{data.action}</div>
    </div>
  );
}

const nodeTypes: NodeTypes = {
  tool: ToolNode,
  action: ActionNode,
};

// ── Graph ↔ React Flow 변환 ──────────────────────────────────

function graphToFlow(graph: ChaeshinToolGraph): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  const actionNodes = new Set<string>();

  // 노드 배치: 그리드 레이아웃
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

  // 엣지 + 액션 노드
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

function flowToGraph(
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

// ── Add Node Dialog ──────────────────────────────────────────

function AddNodeDialog({
  open,
  onOpenChange,
  onAdd,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onAdd: (id: string, tool: string, note: string) => void;
}) {
  const [id, setId] = useState("");
  const [tool, setTool] = useState("");
  const [note, setNote] = useState("");

  const handleAdd = () => {
    if (!id || !tool) return;
    onAdd(id, tool, note);
    setId("");
    setTool("");
    setNote("");
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>노드 추가</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <label className="text-sm font-medium">노드 ID</label>
            <Input value={id} onChange={(e) => setId(e.target.value)} placeholder="n8" />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium">도구 이름</label>
            <Input value={tool} onChange={(e) => setTool(e.target.value)} placeholder="taste_check" />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium">설명</label>
            <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="간보기" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>취소</Button>
          <Button onClick={handleAdd} disabled={!id || !tool}>추가</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Main Component ───────────────────────────────────────────

interface ToolGraphEditorProps {
  graph: ChaeshinToolGraph;
  onChange?: (graph: ChaeshinToolGraph) => void;
  readOnly?: boolean;
  className?: string;
}

export function ToolGraphEditor({
  graph,
  onChange,
  readOnly = false,
  className,
}: ToolGraphEditorProps) {
  const initial = useMemo(() => graphToFlow(graph), [graph]);
  const [nodes, setNodes, onNodesChange] = useNodesState(initial.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initial.edges);
  const [showAddNode, setShowAddNode] = useState(false);
  const [dirty, setDirty] = useState(false);

  const onConnect = useCallback(
    (connection: Connection) => {
      if (readOnly) return;
      setEdges((eds) => addEdge({ ...connection, animated: false, style: { stroke: "#94a3b8" } }, eds));
      setDirty(true);
    },
    [readOnly, setEdges]
  );

  const handleNodesChange: typeof onNodesChange = useCallback(
    (changes) => {
      onNodesChange(changes);
      if (changes.some((c) => c.type === "remove")) setDirty(true);
    },
    [onNodesChange]
  );

  const handleEdgesChange: typeof onEdgesChange = useCallback(
    (changes) => {
      onEdgesChange(changes);
      if (changes.some((c) => c.type === "remove")) setDirty(true);
    },
    [onEdgesChange]
  );

  const handleAddNode = (id: string, tool: string, note: string) => {
    const newNode: Node = {
      id,
      type: "tool",
      position: { x: 200, y: 50 + nodes.length * 100 },
      data: { label: id, tool, note, isEntry: false },
    };
    setNodes((nds) => [...nds, newNode]);
    setDirty(true);
  };

  const handleSave = () => {
    if (!onChange) return;
    const updated = flowToGraph(nodes, edges, graph);
    onChange(updated);
    setDirty(false);
  };

  return (
    <div className={`border rounded-lg overflow-hidden ${className ?? ""}`} style={{ height: 500 }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={readOnly ? undefined : handleNodesChange}
        onEdgesChange={readOnly ? undefined : handleEdgesChange}
        onConnect={onConnect}
        nodeTypes={nodeTypes}
        fitView
        deleteKeyCode={readOnly ? null : "Backspace"}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={16} size={1} />
        <Controls showInteractive={!readOnly} />
        <MiniMap
          nodeStrokeColor={(n) => (n.type === "action" ? "#ef4444" : "#059669")}
          nodeColor={(n) => (n.type === "action" ? "#fef2f2" : "#f0fdf4")}
          style={{ height: 80, width: 120 }}
        />

        {!readOnly && (
          <Panel position="top-right" className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => setShowAddNode(true)}>
              <Plus className="h-4 w-4 mr-1" />
              노드 추가
            </Button>
            {dirty && onChange && (
              <Button size="sm" onClick={handleSave}>
                <Save className="h-4 w-4 mr-1" />
                그래프 저장
              </Button>
            )}
          </Panel>
        )}
      </ReactFlow>

      <AddNodeDialog open={showAddNode} onOpenChange={setShowAddNode} onAdd={handleAddNode} />
    </div>
  );
}
