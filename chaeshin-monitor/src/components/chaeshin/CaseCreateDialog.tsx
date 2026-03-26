"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Separator } from "@/components/ui/separator";
import type { ChaeshinCase, ChaeshinToolGraph } from "@/lib/chaeshin-types";
import { ToolGraphEditor } from "./ToolGraphEditor";
import { Plus, ExternalLink } from "lucide-react";

interface CaseCreateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreate: (newCase: ChaeshinCase) => Promise<void>;
}

const EMPTY_GRAPH: ChaeshinToolGraph = {
  nodes: [],
  edges: [],
  parallel_groups: [],
  entry_nodes: [],
  max_loops: 3,
};

const SESSION_KEY_RESULT = "chaeshin-graph-builder-result";
const SESSION_KEY_DRAFT = "chaeshin-graph-builder-draft";

export function CaseCreateDialog({ open, onOpenChange, onCreate }: CaseCreateDialogProps) {
  const [request, setRequest] = useState("");
  const [category, setCategory] = useState("");
  const [keywords, setKeywords] = useState("");
  const [success, setSuccess] = useState(true);
  const [satisfaction, setSatisfaction] = useState(0.85);
  const [errorReason, setErrorReason] = useState("");
  const [tags, setTags] = useState("");
  const [graph, setGraph] = useState<ChaeshinToolGraph>(EMPTY_GRAPH);
  const [saving, setSaving] = useState(false);

  // Poll for graph builder result when window regains focus
  const checkGraphResult = useCallback(() => {
    const result = sessionStorage.getItem(SESSION_KEY_RESULT);
    if (result) {
      try {
        const parsed = JSON.parse(result) as ChaeshinToolGraph;
        setGraph(parsed);
      } catch { /* ignore */ }
      sessionStorage.removeItem(SESSION_KEY_RESULT);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    const handler = () => checkGraphResult();
    window.addEventListener("focus", handler);
    document.addEventListener("visibilitychange", handler);
    return () => {
      window.removeEventListener("focus", handler);
      document.removeEventListener("visibilitychange", handler);
    };
  }, [open, checkGraphResult]);

  const reset = () => {
    setRequest("");
    setCategory("");
    setKeywords("");
    setSuccess(true);
    setSatisfaction(0.85);
    setErrorReason("");
    setTags("");
    setGraph(EMPTY_GRAPH);
  };

  const openGraphBuilder = () => {
    // Save current graph as draft
    if (graph.nodes.length > 0) {
      sessionStorage.setItem(SESSION_KEY_DRAFT, JSON.stringify(graph));
    }
    window.open("/graph-builder?mode=create", "_blank", "width=1400,height=900");
  };

  const handleCreate = async () => {
    if (!request.trim()) return;
    setSaving(true);
    try {
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
          source: "monitor_ui",
          version: 1,
          tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
        },
      };
      await onCreate(newCase);
      reset();
      onOpenChange(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>새 CBR 케이스 추가</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">요청 (Request) *</label>
            <Input value={request} onChange={(e) => setRequest(e.target.value)} placeholder="김치찌개 2인분 만들어줘" />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label className="text-sm font-medium">카테고리</label>
              <Input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="찌개류" />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">만족도 (0~1)</label>
              <Input type="number" min={0} max={1} step={0.05} value={satisfaction} onChange={(e) => setSatisfaction(Number(e.target.value))} />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium">키워드 (쉼표 구분)</label>
            <Input value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="김치, 찌개, 묵은지" />
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium">태그 (쉼표 구분)</label>
            <Input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="한식, 찌개" />
          </div>

          <Separator />

          <div className="flex items-center gap-2">
            <Checkbox id="create-success" checked={success} onCheckedChange={(v) => setSuccess(!!v)} />
            <label htmlFor="create-success" className="text-sm">성공 케이스</label>
          </div>

          {!success && (
            <div className="space-y-1.5">
              <label className="text-sm font-medium">실패 사유</label>
              <Input value={errorReason} onChange={(e) => setErrorReason(e.target.value)} placeholder="API rate limit 초과" />
            </div>
          )}

          <Separator />

          {/* Tool Graph section */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium">Tool Graph</label>
              <Button variant="outline" size="sm" onClick={openGraphBuilder}>
                <ExternalLink className="h-3.5 w-3.5 mr-1.5" />
                그래프 빌더 열기
              </Button>
            </div>

            {graph.nodes.length > 0 ? (
              <div className="rounded-lg border overflow-hidden">
                <ToolGraphEditor graph={graph} readOnly className="h-[200px]" />
                <div className="px-3 py-1.5 bg-gray-50 border-t text-xs text-muted-foreground">
                  {graph.nodes.length}개 노드, {graph.edges.length}개 엣지
                </div>
              </div>
            ) : (
              <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
                그래프 빌더에서 Tool Graph를 구성하세요
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>취소</Button>
          <Button onClick={handleCreate} disabled={saving || !request.trim()}>
            <Plus className="h-4 w-4 mr-1.5" />
            {saving ? "생성 중..." : "케이스 생성"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
