"use client";

/**
 * main/seed 케이스의 기본 정보와 Tool Graph를 React Flow로 생성·수정하는 화면.
 * URL의 store와 caseId를 기준으로 같은 편집기를 두 저장소에 재사용한다.
 */
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
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Separator } from "@/components/ui/separator";
import type { ChaeshinToolGraph, ChaeshinTool, ChaeshinCase } from "@/lib/chaeshin-types";
import { nodeTypes, edgeTypes, graphToFlow, flowToGraph } from "@/lib/graph-flow-utils";
import { toolApi } from "@/lib/api";
import { ToolPalette } from "@/components/chaeshin/ToolPalette";
import { ToolManageDialog } from "@/components/chaeshin/ToolManageDialog";
import { ArrowLeft, Save, FileText, GitBranch } from "lucide-react";
import { toast } from "sonner";

const EMPTY_GRAPH: ChaeshinToolGraph = {
  nodes: [],
  edges: [],
  parallel_groups: [],
  entry_nodes: [],
  max_loops: 3,
};

// 두 store (main / seed) 가 동일한 응답 모양을 갖도록 정합화돼있음.
// graph-builder 는 query param ?store=seed 면 seed.db 의 케이스를 편집한다.
type StoreName = "main" | "seed";

/** 선택한 저장소와 caseId를 대응하는 API 경로로 변환한다. */
function caseEndpoint(store: StoreName, caseId?: string): string {
  const base = store === "seed" ? "/api/seed" : "/api/chaeshin";
  return caseId ? `${base}/${caseId}` : base;
}

// ── ReactFlowProvider 내부 편집기 ─────────────────────────────

/** React Flow 인스턴스를 사용해 캔버스 상태와 케이스 폼을 함께 관리한다. */
function GraphBuilderInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const reactFlowInstance = useReactFlow();

  const mode = searchParams.get("mode") || "create";
  const caseId = searchParams.get("caseId");
  const store: StoreName = searchParams.get("store") === "seed" ? "seed" : "main";

  // 기본 정보와 그래프 캔버스를 한 화면 상태로 전환한다.
  const [tab, setTab] = useState<"info" | "graph">("info");

  // 도구 레지스트리는 팔레트와 관리 대화상자가 공유한다.
  const [tools, setTools] = useState<ChaeshinTool[]>([]);
  const [showToolManage, setShowToolManage] = useState(false);

  // baseGraph는 화면에서 표현하지 않는 schema/병렬 설정을 저장 시 보존하는 기준이다.
  const [baseGraph, setBaseGraph] = useState<ChaeshinToolGraph>(EMPTY_GRAPH);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const nodeCounter = useRef(0);

  // Case info (기본 정보)
  const [request, setRequest] = useState("");
  const [category, setCategory] = useState("");
  const [keywords, setKeywords] = useState("");
  const [tags, setTags] = useState("");
  const [success, setSuccess] = useState(true);
  const [satisfaction, setSatisfaction] = useState(0.85);
  const [errorReason, setErrorReason] = useState("");
  const [saving, setSaving] = useState(false);

  // tools.json이 아직 없어도 빈 팔레트로 편집기를 계속 사용할 수 있다.
  const fetchTools = useCallback(async () => {
    try {
      const res = await toolApi.getTools();
      setTools(res.data);
    } catch { /* tools.json may not exist yet */ }
  }, []);

  // 수정 모드에서는 도메인 그래프와 폼 값을 각각 React 상태로 복원한다.
  useEffect(() => {
    fetchTools();

    if (caseId) {
      fetch(caseEndpoint(store, caseId))
        .then(async (res) => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return (await res.json()) as ChaeshinCase;
        })
        .then((c) => {
          setBaseGraph(c.solution.tool_graph);
          const flow = graphToFlow(c.solution.tool_graph, onDeleteEdge);
          setNodes(flow.nodes);
          setEdges(flow.edges);
          nodeCounter.current = c.solution.tool_graph.nodes.length;
          // 그래프와 함께 편집할 케이스 기본 정보도 폼에 채운다.
          setRequest(c.problem_features.request);
          setCategory(c.problem_features.category);
          setKeywords(c.problem_features.keywords.join(", "));
          setTags(c.metadata.tags.join(", "));
          setSuccess(c.outcome.success);
          setSatisfaction(c.outcome.user_satisfaction);
          setErrorReason(c.outcome.error_reason || "");
        })
        .catch(() => toast.error("케이스를 불러올 수 없습니다"));
    }
  }, [caseId, store, fetchTools, setNodes, setEdges]);

  // 커스텀 엣지의 삭제 버튼에서 해당 React Flow 엣지만 제거한다.
  const onDeleteEdge = useCallback(
    (edgeId: string) => {
      setEdges((eds) => eds.filter((e) => e.id !== edgeId));
    },
    [setEdges]
  );

  // 새 연결에도 삭제 callback을 주입해 기존 엣지와 같은 동작을 보장한다.
  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) => addEdge({
        ...connection,
        type: "deletable",
        animated: false,
        style: { stroke: "#94a3b8" },
        data: { onDelete: onDeleteEdge },
      }, eds));
    },
    [setEdges, onDeleteEdge]
  );

  // 팔레트의 + 버튼으로 추가할 때는 격자형 기본 좌표를 부여한다.
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
      if (tab !== "graph") setTab("graph");
    },
    [setNodes, tab]
  );

  // 브라우저 기본 drop을 허용하고 팔레트가 지정한 이동 효과를 표시한다.
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
      // 화면 좌표를 현재 확대·이동 상태가 반영된 Flow 좌표로 변환한다.
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

  // 화면의 Flow 상태를 도메인 그래프로 되돌린 뒤 create/edit 경로로 저장한다.
  const handleSave = useCallback(async () => {
    if (mode === "create" && !request.trim()) {
      toast.error("요청(Request)을 입력하세요");
      setTab("info");
      return;
    }

    setSaving(true);
    const graph = flowToGraph(nodes, edges, baseGraph);

    try {
      if (caseId) {
        // 수정 모드에서는 선택한 저장소의 동일 caseId를 갱신한다.
        const payload = {
          problem_features: {
            request,
            category,
            keywords: keywords.split(",").map((k) => k.trim()).filter(Boolean),
            constraints: [],
            context: {},
          },
          solution: { tool_graph: graph },
          outcome: {
            success,
            result_summary: "",
            tools_executed: graph.nodes.length,
            loops_triggered: 0,
            total_time_ms: 0,
            user_satisfaction: success ? satisfaction : 0,
            error_reason: success ? "" : errorReason,
            details: {},
          },
          metadata: {
            tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
          },
        };
        const res = await fetch(caseEndpoint(store, caseId), {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        toast.success(
          store === "seed" ? "Seed 케이스 저장됨" : "케이스가 저장되었습니다",
        );
      } else {
        // 생성 모드에서는 클라이언트에서 신규 caseId와 기본 metadata를 구성한다.
        const newCase: ChaeshinCase = {
          problem_features: {
            request,
            category,
            keywords: keywords.split(",").map((k) => k.trim()).filter(Boolean),
            constraints: [],
            context: {},
          },
          solution: { tool_graph: graph },
          outcome: {
            success,
            result_summary: "",
            tools_executed: graph.nodes.length,
            loops_triggered: 0,
            total_time_ms: 0,
            user_satisfaction: success ? satisfaction : 0,
            error_reason: success ? "" : errorReason,
            details: {},
          },
          metadata: {
            case_id: crypto.randomUUID(),
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            used_count: 0,
            avg_satisfaction: 0,
            source: store === "seed" ? "seed:monitor_ui" : "monitor_ui",
            version: 3,
            tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
          },
        };
        const res = await fetch(caseEndpoint(store), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(newCase),
        });
        if (!res.ok) throw new Error();
        toast.success(
          store === "seed"
            ? "새 Seed 케이스가 생성되었습니다"
            : "새 케이스가 생성되었습니다",
        );
      }

      // 팝업으로 열렸으면 닫고, 직접 진입했으면 원래 저장소 목록으로 이동한다.
      if (window.opener) {
        window.close();
      } else {
        router.push(store === "seed" ? "/seed" : "/");
      }
    } catch {
      toast.error("저장에 실패했습니다");
    } finally {
      setSaving(false);
    }
  }, [nodes, edges, baseGraph, caseId, mode, store, request, category, keywords, tags, success, satisfaction, errorReason, router]);

  const handleBack = () => {
    if (window.opener) {
      window.close();
    } else {
      router.push(store === "seed" ? "/seed" : "/");
    }
  };

  return (
    <div className="h-screen flex flex-col" style={{ backgroundColor: "#ffffff" }}>
      {/* 편집기 헤더 */}
      <div className="flex items-center gap-3 px-4 py-2.5 border-b shrink-0" style={{ backgroundColor: "#ffffff" }}>
        <Button variant="ghost" size="sm" onClick={handleBack}>
          <ArrowLeft className="h-4 w-4 mr-1" />
          돌아가기
        </Button>

        {/* 기본 정보·그래프 전환 버튼 */}
        <div className="flex items-center gap-1 ml-2 bg-gray-100 rounded-lg p-0.5">
          <button
            onClick={() => setTab("info")}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md transition-colors ${
              tab === "info"
                ? "bg-white text-gray-900 font-medium shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            <FileText className="h-3.5 w-3.5" />
            기본 정보
          </button>
          <button
            onClick={() => setTab("graph")}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md transition-colors ${
              tab === "graph"
                ? "bg-white text-gray-900 font-medium shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            <GitBranch className="h-3.5 w-3.5" />
            그래프
            {nodes.length > 0 && (
              <span className="text-[10px] bg-gray-200 text-gray-600 px-1.5 rounded-full">{nodes.length}</span>
            )}
          </button>
        </div>

        <div className="flex-1" />

        <Button onClick={handleSave} disabled={saving}>
          <Save className="h-4 w-4 mr-1.5" />
          {saving ? "저장 중..." : caseId ? "수정 저장" : "케이스 생성"}
        </Button>
      </div>

      {/* 선택한 탭의 편집 영역 */}
      <div className="flex-1 flex min-h-0">
        {tab === "graph" ? (
          <>
            {/* React Flow 캔버스 */}
            <div className="flex-1" style={{ backgroundColor: "#ffffff" }} onDragOver={onDragOver} onDrop={onDrop}>
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                nodeTypes={nodeTypes}
                edgeTypes={edgeTypes}
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
                    <div className="bg-white border rounded-lg px-6 py-4 text-center shadow-sm mt-4">
                      <p className="text-sm font-medium text-gray-700">오른쪽 팔레트에서 도구를 드래그하거나 + 버튼을 클릭하세요</p>
                      <p className="text-xs text-gray-400 mt-1">도구가 없으면 &quot;도구 관리&quot;에서 먼저 등록하세요</p>
                    </div>
                  </Panel>
                )}
              </ReactFlow>
            </div>

            {/* 오른쪽 도구 팔레트 */}
            <div className="w-[280px] shrink-0">
              <ToolPalette
                tools={tools}
                onAddNode={handleAddNodeFromTool}
                onManageTools={() => setShowToolManage(true)}
              />
            </div>
          </>
        ) : (
          /* 케이스 기본 정보 탭 */
          <div className="flex-1 overflow-y-auto" style={{ backgroundColor: "#ffffff" }}>
            <div className="max-w-xl mx-auto p-8 space-y-5">
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-gray-700">요청 (Request) *</label>
                <Input value={request} onChange={(e) => setRequest(e.target.value)} placeholder="김치찌개 2인분 만들어줘" />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-gray-700">카테고리</label>
                  <Input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="찌개류" />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-gray-700">만족도 (0~1)</label>
                  <Input type="number" min={0} max={1} step={0.05} value={satisfaction} onChange={(e) => setSatisfaction(Number(e.target.value))} />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-sm font-medium text-gray-700">키워드 (쉼표 구분)</label>
                <Input value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="김치, 찌개, 묵은지" />
              </div>

              <div className="space-y-1.5">
                <label className="text-sm font-medium text-gray-700">태그 (쉼표 구분)</label>
                <Input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="한식, 찌개" />
              </div>

              <Separator />

              <div className="flex items-center gap-2">
                <Checkbox id="builder-success" checked={success} onCheckedChange={(v) => setSuccess(!!v)} />
                <label htmlFor="builder-success" className="text-sm text-gray-700">성공 케이스</label>
              </div>

              {!success && (
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-gray-700">실패 사유</label>
                  <Input value={errorReason} onChange={(e) => setErrorReason(e.target.value)} placeholder="API rate limit 초과" />
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* 도구 레지스트리 관리 대화상자 */}
      <ToolManageDialog
        open={showToolManage}
        onOpenChange={setShowToolManage}
        tools={tools}
        onRefresh={fetchTools}
      />
    </div>
  );
}

// ── ReactFlowProvider를 포함한 페이지 래퍼 ───────────────────

/** navigation query와 React Flow context가 준비된 뒤 내부 편집기를 렌더링한다. */
export default function GraphBuilderPage() {
  return (
    <Suspense fallback={<div className="h-screen flex items-center justify-center text-gray-400">로딩 중...</div>}>
      <ReactFlowProvider>
        <GraphBuilderInner />
      </ReactFlowProvider>
    </Suspense>
  );
}
