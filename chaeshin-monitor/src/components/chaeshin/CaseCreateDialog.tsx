"use client";

import { useState } from "react";
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
import { Plus } from "lucide-react";

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

export function CaseCreateDialog({ open, onOpenChange, onCreate }: CaseCreateDialogProps) {
  const [tab, setTab] = useState<"info" | "graph">("info");
  const [request, setRequest] = useState("");
  const [category, setCategory] = useState("");
  const [keywords, setKeywords] = useState("");
  const [success, setSuccess] = useState(true);
  const [satisfaction, setSatisfaction] = useState(0.85);
  const [errorReason, setErrorReason] = useState("");
  const [tags, setTags] = useState("");
  const [graph, setGraph] = useState<ChaeshinToolGraph>(EMPTY_GRAPH);
  const [saving, setSaving] = useState(false);

  const reset = () => {
    setTab("info");
    setRequest("");
    setCategory("");
    setKeywords("");
    setSuccess(true);
    setSatisfaction(0.85);
    setErrorReason("");
    setTags("");
    setGraph(EMPTY_GRAPH);
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
      <DialogContent className="max-w-4xl h-[85vh] flex flex-col p-0 gap-0 overflow-hidden">
        <DialogHeader className="px-6 pt-6 pb-4 border-b shrink-0">
          <DialogTitle>새 CBR 케이스 추가</DialogTitle>
          {/* Custom tab bar */}
          <div className="flex gap-1 mt-3">
            <button
              onClick={() => setTab("info")}
              className={`px-4 py-1.5 text-sm rounded-md transition-colors ${
                tab === "info"
                  ? "bg-primary text-primary-foreground font-medium"
                  : "text-muted-foreground hover:bg-muted"
              }`}
            >
              기본 정보
            </button>
            <button
              onClick={() => setTab("graph")}
              className={`px-4 py-1.5 text-sm rounded-md transition-colors ${
                tab === "graph"
                  ? "bg-primary text-primary-foreground font-medium"
                  : "text-muted-foreground hover:bg-muted"
              }`}
            >
              Tool Graph ({graph.nodes.length} nodes)
            </button>
          </div>
        </DialogHeader>

        {/* Content area — flex-1 fills remaining space */}
        <div className="flex-1 min-h-0 overflow-hidden">
          {tab === "info" ? (
            <div className="p-6 space-y-4 overflow-y-auto h-full">
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
            </div>
          ) : (
            /* Graph tab: ToolGraphEditor fills entire area */
            <div className="h-full w-full">
              <ToolGraphEditor graph={graph} onChange={setGraph} className="h-full w-full rounded-none border-0" />
            </div>
          )}
        </div>

        <DialogFooter className="px-6 py-4 border-t shrink-0">
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
