"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
  type Node,
  type Edge,
  type Connection,
  Panel,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { Button } from "@/components/ui/button";
import type { ChaeshinToolGraph, ChaeshinTool } from "@/lib/chaeshin-types";
import { nodeTypes, graphToFlow, flowToGraph } from "@/lib/graph-flow-utils";
import { api, toolApi } from "@/lib/api";
import { ToolPalette } from "@/components/chaeshin/ToolPalette";
import { ToolManageDialog } from "@/components/chaeshin/ToolManageDialog";
import { ArrowLeft, Save } from "lucide-react";
import { toast } from "sonner";

const EMPTY_GRAPH: ChaeshinToolGraph = {
  nodes: [],
  edges: [],
  parallel_groups: [],
  entry_nodes: [],
  max_loops: 3,
};

const SESSION_KEY_DRAFT = "chaeshin-graph-builder-draft";
const SESSION_KEY_RESULT = "chaeshin-graph-builder-result";

// ── Inner component (needs ReactFlowProvider) ─────────────────

function GraphBuilderInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const reactFlowInstance = useReactFlow();

  const mode = searchParams.get("mode") || "create";
  const caseId = searchParams.get("caseId");

  const [tools, setTools] = useState<ChaeshinTool[]>([]);
  const [showToolManage, setShowToolManage] = useState(false);
  const [baseGraph, setBaseGraph] = useState<ChaeshinToolGraph>(EMPTY_GRAPH);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const nodeCounter = useRef(0);

  // Load tools
  const fetchTools = useCallback(async () => {
    try {
      const res = await toolApi.getTools();
      setTools(res.data);
    } catch {
      /* tools.json may not exist yet */
    }
  }, []);

  // Load initial graph
  useEffect(() => {
    fetchTools();

    const loadGraph = async () => {
      let graph = EMPTY_GRAPH;

      if (caseId) {
        // Edit mode: load from API
        try {
          const c = await api.getCase(caseId);
          graph = c.solution.tool_graph;
        } catch {
          toast.error("케이스를 불러올 수 없습니다");
        }
      } else {
        // Create mode: check sessionStorage draft
        const draft = sessionStorage.getItem(SESSION_KEY_DRAFT);
        if (draft) {
          try {
            graph = JSON.parse(draft);
          } catch { /* ignore */ }
        }
      }

      setBaseGraph(graph);
      const flow = graphToFlow(graph);
      setNodes(flow.nodes);
      setEdges(flow.edges);
      nodeCounter.current = graph.nodes.length;
    };

    loadGraph();
  }, [caseId, fetchTools, setNodes, setEdges]);

  // Connect edges
  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) => addEdge({ ...connection, animated: false, style: { stroke: "#94a3b8" } }, eds));
    },
    [setEdges]
  );

  // Add node from palette
  const handleAddNodeFromTool = useCallback(
    (tool: ChaeshinTool) => {
      nodeCounter.current += 1;
      const id = `n${nodeCounter.current}`;
      const newNode: Node = {
        id,
        type: "tool",
        position: { x: 100 + (nodeCounter.current % 4) * 200, y: 80 + Math.floor(nodeCounter.current / 4) * 140 },
        data: { label: id, tool: tool.name, note: tool.display_name, isEntry: false },
      };
      setNodes((nds) => [...nds, newNode]);
    },
    [setNodes]
  );

  // Drop handler
  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const toolData = e.dataTransfer.getData("application/chaeshin-tool");
      if (!toolData) return;

      const tool: ChaeshinTool = JSON.parse(toolData);
      const position = reactFlowInstance.screenToFlowPosition({ x: e.clientX, y: e.clientY });

      nodeCounter.current += 1;
      const id = `n${nodeCounter.current}`;
      const newNode: Node = {
        id,
        type: "tool",
        position,
        data: { label: id, tool: tool.name, note: tool.display_name, isEntry: false },
      };
      setNodes((nds) => [...nds, newNode]);
    },
    [reactFlowInstance, setNodes]
  );

  // Save
  const handleSave = useCallback(() => {
    const graph = flowToGraph(nodes, edges, baseGraph);

    if (caseId) {
      // Edit mode: update case via API
      api
        .updateCase(caseId, { solution: { tool_graph: graph } })
        .then(() => {
          toast.success("그래프가 저장되었습니다");
          window.close();
        })
        .catch(() => toast.error("저장에 실패했습니다"));
    } else {
      // Create mode: save to sessionStorage and close
      sessionStorage.setItem(SESSION_KEY_RESULT, JSON.stringify(graph));
      sessionStorage.removeItem(SESSION_KEY_DRAFT);
      toast.success("그래프가 저장되었습니다");
      window.close();
    }
  }, [nodes, edges, baseGraph, caseId]);

  const handleBack = () => {
    if (window.opener) {
      window.close();
    } else {
      router.push("/");
    }
  };

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b bg-white shrink-0">
        <Button variant="ghost" size="sm" onClick={handleBack}>
          <ArrowLeft className="h-4 w-4 mr-1" />
          돌아가기
        </Button>
        <div className="flex-1">
          <h1 className="text-lg font-bold">그래프 빌더</h1>
          <p className="text-xs text-muted-foreground">
            {caseId ? `케이스 수정: ${caseId.slice(0, 8)}...` : "새 Tool Graph 생성"}
          </p>
        </div>
        <Button onClick={handleSave}>
          <Save className="h-4 w-4 mr-1.5" />
          저장
        </Button>
      </div>

      {/* Main area */}
      <div className="flex-1 flex min-h-0">
        {/* Canvas */}
        <div className="flex-1" onDragOver={onDragOver} onDrop={onDrop}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            nodeTypes={nodeTypes}
            fitView
            deleteKeyCode="Backspace"
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={16} size={1} />
            <Controls />
            <MiniMap
              nodeStrokeColor={(n) => (n.type === "action" ? "#ef4444" : "#059669")}
              nodeColor={(n) => (n.type === "action" ? "#fef2f2" : "#f0fdf4")}
              style={{ height: 80, width: 120 }}
            />
            {nodes.length === 0 && (
              <Panel position="top-center">
                <div className="bg-white/90 border rounded-lg px-6 py-4 text-center shadow-sm">
                  <p className="text-sm text-muted-foreground">오른쪽 팔레트에서 도구를 드래그하거나 + 버튼을 클릭하세요</p>
                </div>
              </Panel>
            )}
          </ReactFlow>
        </div>

        {/* Right panel: Tool palette */}
        <div className="w-[280px] shrink-0">
          <ToolPalette
            tools={tools}
            onAddNode={handleAddNodeFromTool}
            onManageTools={() => setShowToolManage(true)}
          />
        </div>
      </div>

      {/* Tool management dialog */}
      <ToolManageDialog
        open={showToolManage}
        onOpenChange={setShowToolManage}
        tools={tools}
        onRefresh={fetchTools}
      />
    </div>
  );
}

// ── Page wrapper with ReactFlowProvider ───────────────────────

export default function GraphBuilderPage() {
  return (
    <Suspense fallback={<div className="h-screen flex items-center justify-center text-muted-foreground">로딩 중...</div>}>
      <ReactFlowProvider>
        <GraphBuilderInner />
      </ReactFlowProvider>
    </Suspense>
  );
}
