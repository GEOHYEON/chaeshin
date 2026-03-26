"use client";

import { useState, useEffect, useCallback } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { StatCard } from "@/components/common/StatCard";
import { CaseDetailDialog } from "./CaseDetailDialog";
import { CaseEditDialog } from "./CaseEditDialog";
import {
  type ChaeshinCase,
  type ChaeshinStats,
  computeChaeshinStats,
} from "@/lib/chaeshin-types";
import { api } from "@/lib/api";
import {
  Database,
  CheckCircle,
  TrendingUp,
  RefreshCw,
  Search,
  Pencil,
  Trash2,
  Eye,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";

export function ChaeshinTab() {
  const [cases, setCases] = useState<ChaeshinCase[]>([]);
  const [stats, setStats] = useState<ChaeshinStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterSuccess, setFilterSuccess] = useState<string>("all");
  const [detailCase, setDetailCase] = useState<ChaeshinCase | null>(null);
  const [editCase, setEditCase] = useState<ChaeshinCase | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.getCases();
      setCases(res.data as ChaeshinCase[]);
      setStats(computeChaeshinStats(res.data as ChaeshinCase[]));
    } catch {
      toast.error("케이스를 불러오는데 실패했습니다");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const filtered = cases.filter((c) => {
    if (filterSuccess === "success" && !c.outcome?.success) return false;
    if (filterSuccess === "fail" && c.outcome?.success) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return (
        c.problem_features?.request?.toLowerCase().includes(q) ||
        c.problem_features?.category?.toLowerCase().includes(q) ||
        c.problem_features?.keywords?.some((kw: string) => kw.toLowerCase().includes(q))
      );
    }
    return true;
  });

  const handleSave = async (updated: ChaeshinCase) => {
    try {
      await api.updateCase(updated.metadata.case_id, updated);
      toast.success("케이스가 수정되었습니다");
      fetchData();
    } catch {
      toast.error("수정에 실패했습니다");
    }
  };

  const handleDelete = async (caseId: string) => {
    try {
      await api.deleteCase(caseId);
      toast.success("케이스가 삭제되었습니다");
      fetchData();
    } catch {
      toast.error("삭제에 실패했습니다");
    }
  };

  return (
    <div className="space-y-6">
      {/* Stats */}
      {stats && (
        <div className="grid gap-4 grid-cols-2 md:grid-cols-4">
          <StatCard
            title="전체 케이스"
            value={stats.totalCases}
            icon={<Database className="h-5 w-5 text-blue-500" />}
          />
          <StatCard
            title="성공률"
            value={`${(stats.successRate * 100).toFixed(0)}%`}
            description={`성공 ${stats.successCount} / 실패 ${stats.failCount}`}
            icon={<CheckCircle className="h-5 w-5 text-green-500" />}
          />
          <StatCard
            title="평균 만족도"
            value={`${(stats.avgSatisfaction * 100).toFixed(0)}%`}
            icon={<TrendingUp className="h-5 w-5 text-purple-500" />}
          />
          <StatCard
            title="총 재사용"
            value={stats.totalReuses}
            description={`${stats.categories.length}개 카테고리`}
            icon={<RefreshCw className="h-5 w-5 text-orange-500" />}
          />
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-3 items-center">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="검색 (요청, 카테고리, 키워드)"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select value={filterSuccess} onValueChange={setFilterSuccess}>
          <SelectTrigger className="w-[140px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">전체</SelectItem>
            <SelectItem value="success">성공만</SelectItem>
            <SelectItem value="fail">실패만</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" onClick={fetchData} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-1.5 ${loading ? "animate-spin" : ""}`} />
          새로고침
        </Button>
      </div>

      {/* Table */}
      {loading ? (
        <div className="text-center py-12 text-muted-foreground">로딩 중...</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          Chaeshin CBR 케이스가 없습니다
        </div>
      ) : (
        <div className="border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="text-left px-4 py-2 font-medium">요청</th>
                <th className="text-left px-4 py-2 font-medium">상태</th>
                <th className="text-left px-4 py-2 font-medium">만족도</th>
                <th className="text-left px-4 py-2 font-medium">그래프</th>
                <th className="text-left px-4 py-2 font-medium">사용</th>
                <th className="text-left px-4 py-2 font-medium">태그</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((c, i) => (
                <tr
                  key={c.metadata?.case_id ?? i}
                  className="border-t hover:bg-muted/30 cursor-pointer"
                  onClick={() => setDetailCase(c)}
                >
                  <td className="px-4 py-3 max-w-[300px]">
                    <p className="truncate font-medium">{c.problem_features?.request}</p>
                    <p className="text-xs text-muted-foreground truncate">{c.problem_features?.category}</p>
                  </td>
                  <td className="px-4 py-3">
                    {c.outcome?.success ? (
                      <Badge className="bg-green-100 text-green-700 hover:bg-green-100">성공</Badge>
                    ) : (
                      <Badge className="bg-red-100 text-red-700 hover:bg-red-100">실패</Badge>
                    )}
                  </td>
                  <td className="px-4 py-3 font-mono">
                    {((c.outcome?.user_satisfaction ?? 0) * 100).toFixed(0)}%
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    {c.solution?.tool_graph?.nodes?.length ?? 0}N / {c.solution?.tool_graph?.edges?.length ?? 0}E
                  </td>
                  <td className="px-4 py-3 font-mono">{c.metadata?.used_count ?? 0}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {(c.metadata?.tags ?? []).slice(0, 3).map((tag: string) => (
                        <Badge key={tag} variant="outline" className="text-xs">{tag}</Badge>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1">
                      <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); setDetailCase(c); }}>
                        <Eye className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); setEditCase(c); }}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="sm" onClick={(e) => {
                        e.stopPropagation();
                        if (confirm("이 케이스를 삭제하시겠습니까?")) handleDelete(c.metadata?.case_id);
                      }}>
                        <Trash2 className="h-4 w-4 text-red-500" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <CaseDetailDialog caseData={detailCase} open={!!detailCase} onOpenChange={(o) => !o && setDetailCase(null)} />
      <CaseEditDialog caseData={editCase} open={!!editCase} onOpenChange={(o) => !o && setEditCase(null)} onSave={handleSave} />
    </div>
  );
}
