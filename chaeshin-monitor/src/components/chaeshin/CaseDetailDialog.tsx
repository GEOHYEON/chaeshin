"use client";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  type ChaeshinCase,
  type ChaeshinToolGraph,
} from "@/lib/chaeshin-types";
import { ToolGraphEditor } from "./ToolGraphEditor";
import {
  CheckCircle,
  XCircle,
  Clock,
  RefreshCw,
  Tag,
} from "lucide-react";

interface CaseDetailDialogProps {
  caseData: ChaeshinCase | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onGraphChange?: (graph: ChaeshinToolGraph) => void;
}

export function CaseDetailDialog({
  caseData,
  open,
  onOpenChange,
  onGraphChange,
}: CaseDetailDialogProps) {
  if (!caseData) return null;

  const { problem_features: pf, solution, outcome, metadata } = caseData;
  const graph = solution.tool_graph;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {outcome.success ? (
              <CheckCircle className="h-5 w-5 text-green-500" />
            ) : (
              <XCircle className="h-5 w-5 text-red-500" />
            )}
            {pf.request}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* Problem Features */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Problem Features</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <div className="flex gap-2">
                <span className="text-muted-foreground w-20 shrink-0">카테고리</span>
                <Badge variant="outline">{pf.category || "—"}</Badge>
              </div>
              <div className="flex gap-2">
                <span className="text-muted-foreground w-20 shrink-0">키워드</span>
                <div className="flex flex-wrap gap-1">
                  {pf.keywords.map((kw) => (
                    <Badge key={kw} variant="secondary" className="text-xs">
                      {kw}
                    </Badge>
                  ))}
                </div>
              </div>
              {pf.constraints.length > 0 && (
                <div className="flex gap-2">
                  <span className="text-muted-foreground w-20 shrink-0">제약</span>
                  <span>{pf.constraints.join(", ")}</span>
                </div>
              )}
              {Object.keys(pf.context).length > 0 && (
                <div className="flex gap-2">
                  <span className="text-muted-foreground w-20 shrink-0">컨텍스트</span>
                  <pre className="text-xs bg-muted p-2 rounded flex-1 overflow-auto">
                    {JSON.stringify(pf.context, null, 2)}
                  </pre>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Tool Graph — React Flow Editor */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">
                Tool Graph ({graph.nodes.length} nodes, {graph.edges.length} edges)
                {!onGraphChange && (
                  <span className="text-xs text-muted-foreground font-normal ml-2">읽기 전용</span>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ToolGraphEditor
                graph={graph}
                onChange={onGraphChange}
                readOnly={!onGraphChange}
              />

              {graph.parallel_groups.length > 0 && (
                <>
                  <Separator className="my-3" />
                  <p className="text-xs text-muted-foreground">
                    병렬 그룹: {graph.parallel_groups.map((g) => `[${g.join(", ")}]`).join(" ")}
                  </p>
                </>
              )}
            </CardContent>
          </Card>

          {/* Outcome */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Outcome</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="flex items-center gap-1.5">
                  {outcome.success ? (
                    <CheckCircle className="h-4 w-4 text-green-500" />
                  ) : (
                    <XCircle className="h-4 w-4 text-red-500" />
                  )}
                  <span>{outcome.success ? "성공" : "실패"}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-muted-foreground">만족도:</span>
                  <span className="font-medium">
                    {(outcome.user_satisfaction * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="flex items-center gap-1.5">
                  <Clock className="h-4 w-4 text-muted-foreground" />
                  <span>{outcome.total_time_ms}ms</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <RefreshCw className="h-4 w-4 text-muted-foreground" />
                  <span>루프 {outcome.loops_triggered}회</span>
                </div>
              </div>
              {outcome.result_summary && (
                <p className="text-muted-foreground">{outcome.result_summary}</p>
              )}
              {outcome.error_reason && (
                <div className="bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900 rounded p-2 text-red-700 dark:text-red-400 text-xs">
                  {outcome.error_reason}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Metadata */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Metadata</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <span className="text-muted-foreground">Case ID: </span>
                  <code className="font-mono">{metadata.case_id.slice(0, 8)}...</code>
                </div>
                <div>
                  <span className="text-muted-foreground">Source: </span>
                  <span>{metadata.source}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">사용 횟수: </span>
                  <span className="font-medium">{metadata.used_count}회</span>
                </div>
                <div>
                  <span className="text-muted-foreground">평균 만족도: </span>
                  <span>{(metadata.avg_satisfaction * 100).toFixed(0)}%</span>
                </div>
                <div>
                  <span className="text-muted-foreground">생성: </span>
                  <span>{new Date(metadata.created_at).toLocaleDateString("ko-KR")}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">수정: </span>
                  <span>{new Date(metadata.updated_at).toLocaleDateString("ko-KR")}</span>
                </div>
              </div>
              {metadata.tags.length > 0 && (
                <div className="flex items-center gap-1.5 flex-wrap">
                  <Tag className="h-3 w-3 text-muted-foreground" />
                  {metadata.tags.map((tag) => (
                    <Badge key={tag} variant="outline" className="text-xs">
                      {tag}
                    </Badge>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </DialogContent>
    </Dialog>
  );
}
