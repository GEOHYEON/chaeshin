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
import type { ChaeshinToolGraph } from "@/lib/chaeshin-types";
import { nodeTypes, graphToFlow, flowToGraph } from "@/lib/graph-flow-utils";
import { Plus, Save } from "lucide-react";

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
    <div className={`border rounded-lg overflow-hidden ${className ?? "h-[500px]"}`}>
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
