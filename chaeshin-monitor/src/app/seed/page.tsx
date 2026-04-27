"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Sprout, Sparkles, Upload, Download, Trash2, Filter, FileJson, GitBranch } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";

import { SeedGenerateDialog } from "@/components/chaeshin/SeedGenerateDialog";
import { SeedPromoteDialog } from "@/components/chaeshin/SeedPromoteDialog";

interface SeedCase {
  problem_features: {
    request: string;
    category?: string;
    keywords?: string[];
  };
  solution: {
    tool_graph?: {
      nodes?: Array<{ id?: string; tool?: string; note?: string }>;
      edges?: Array<unknown>;
    };
  };
  outcome: {
    status?: string;
  };
  metadata: {
    case_id: string;
    source?: string;
    created_at?: string;
  };
}

export default function SeedPage() {
  const [cases, setCases] = useState<SeedCase[]>([]);
  const [loading, setLoading] = useState(false);
  const [topicFilter, setTopicFilter] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [generateOpen, setGenerateOpen] = useState(false);
  const [promoteOpen, setPromoteOpen] = useState(false);
  const [pathDialog, setPathDialog] = useState<null | "export" | "import">(null);
  const [pathInput, setPathInput] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (topicFilter) params.set("topic", topicFilter);
      const res = await fetch(`/api/seed?${params}`);
      const data = await res.json();
      setCases(data.data || []);
    } finally {
      setLoading(false);
    }
  }, [topicFilter]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const filtered = useMemo(() => {
    if (!search) return cases;
    const q = search.toLowerCase();
    return cases.filter((c) => {
      const r = c.problem_features.request.toLowerCase();
      const cat = (c.problem_features.category || "").toLowerCase();
      return r.includes(q) || cat.includes(q);
    });
  }, [cases, search]);

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAllVisible = () => {
    setSelected(new Set(filtered.map((c) => c.metadata.case_id)));
  };

  const clearSelection = () => setSelected(new Set());

  const handleDelete = async (caseId: string) => {
    if (!confirm("이 시드 케이스를 삭제할까요?")) return;
    const res = await fetch(`/api/seed/${caseId}`, { method: "DELETE" });
    if (!res.ok) {
      toast.error("삭제 실패");
      return;
    }
    toast.success("삭제됨");
    refresh();
  };

  const openExportDialog = () => {
    setPathInput(`/tmp/chaeshin-seed-${new Date().toISOString().slice(0, 10)}.json`);
    setPathDialog("export");
  };

  const openImportDialog = () => {
    setPathInput("");
    setPathDialog("import");
  };

  const runExport = async () => {
    const res = await fetch("/api/seed/export", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ path: pathInput }),
    });
    const data = await res.json();
    if (!res.ok) {
      toast.error(data.error || "Export 실패");
      return;
    }
    toast.success(`${data.count}건 → ${data.path}`);
    setPathDialog(null);
  };

  const runImport = async () => {
    const res = await fetch("/api/seed/import", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ path: pathInput }),
    });
    const data = await res.json();
    if (!res.ok) {
      toast.error(data.error || "Import 실패");
      return;
    }
    toast.success(`${data.added}건 가져옴`);
    setPathDialog(null);
    refresh();
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="sticky top-0 z-30 border-b bg-white">
        <div className="flex items-center gap-3 px-6 h-14 max-w-7xl mx-auto">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-amber-500 text-white">
            <Sprout className="h-4 w-4" />
          </div>
          <div>
            <h1 className="text-base font-semibold tracking-tight">Seed Bootstrapping</h1>
            <p className="text-[11px] text-gray-400 leading-none">
              Cold-start 시드 케이스 생성 → 검토 → main DB promote
            </p>
          </div>
          <nav className="ml-auto flex items-center gap-4 text-sm">
            <Link href="/" className="text-gray-500 hover:text-gray-900">Cases</Link>
            <Link href="/events" className="text-gray-500 hover:text-gray-900">Events</Link>
            <Link href="/hierarchy" className="text-gray-500 hover:text-gray-900">Hierarchy</Link>
            <Link href="/seed" className="font-medium text-gray-900">Seed</Link>
          </nav>
        </div>
      </header>

      <main className="p-6 max-w-7xl mx-auto space-y-4">
        {/* Action bar */}
        <div className="flex flex-wrap items-center gap-2 bg-white border rounded p-3">
          <Button onClick={() => setGenerateOpen(true)}>
            <Sparkles className="h-4 w-4 mr-2" />
            Generate
          </Button>
          <Separator orientation="vertical" className="h-6" />
          <Button variant="outline" onClick={openExportDialog}>
            <Download className="h-4 w-4 mr-2" />
            Export
          </Button>
          <Button variant="outline" onClick={openImportDialog}>
            <FileJson className="h-4 w-4 mr-2" />
            Import
          </Button>
          <Separator orientation="vertical" className="h-6" />
          <Button
            variant="default"
            disabled={selected.size === 0}
            onClick={() => setPromoteOpen(true)}
            className="bg-emerald-600 hover:bg-emerald-700"
          >
            <Upload className="h-4 w-4 mr-2" />
            Promote {selected.size > 0 ? `(${selected.size})` : ""}
          </Button>

          <div className="ml-auto flex items-center gap-2 text-xs text-gray-500">
            <span>총 {cases.length}건 / 표시 {filtered.length}건 / 선택 {selected.size}건</span>
            {selected.size > 0 && (
              <Button variant="ghost" size="sm" onClick={clearSelection}>
                선택 해제
              </Button>
            )}
          </div>
        </div>

        {/* Filter bar */}
        <div className="flex items-center gap-2 bg-white border rounded p-3">
          <Filter className="h-4 w-4 text-gray-400" />
          <Input
            placeholder="source 토픽으로 필터 (예: T2DM)"
            value={topicFilter}
            onChange={(e) => setTopicFilter(e.target.value)}
            className="max-w-xs"
          />
          <Input
            placeholder="request / category 검색"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="max-w-xs"
          />
          <Button variant="ghost" size="sm" onClick={selectAllVisible}>
            표시 항목 전체 선택
          </Button>
        </div>

        {/* Case list */}
        {loading ? (
          <div className="bg-white border rounded p-8 text-center text-gray-400 text-sm">
            불러오는 중…
          </div>
        ) : filtered.length === 0 ? (
          <div className="bg-white border rounded p-8 text-center text-gray-500 text-sm">
            <Sprout className="h-6 w-6 mx-auto mb-2 text-gray-300" />
            아직 시드 케이스가 없습니다. <strong>Generate</strong> 로 시작하세요.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {filtered.map((c) => {
              const cid = c.metadata.case_id;
              const checked = selected.has(cid);
              const nodes = c.solution.tool_graph?.nodes || [];
              const edges = c.solution.tool_graph?.edges || [];
              const tools = Array.from(
                new Set(nodes.map((n) => n.tool || "?").slice(0, 5)),
              );
              return (
                <div
                  key={cid}
                  className={`border rounded p-3 bg-white hover:shadow-sm transition ${
                    checked ? "ring-2 ring-amber-400 border-amber-400" : ""
                  }`}
                >
                  <div className="flex items-start gap-2">
                    <Checkbox
                      checked={checked}
                      onCheckedChange={() => toggleSelect(cid)}
                      className="mt-1"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <Badge variant="outline" className="text-[10px] uppercase">
                          {c.metadata.source || "seed"}
                        </Badge>
                        {c.problem_features.category && (
                          <Badge variant="secondary" className="text-[10px]">
                            {c.problem_features.category}
                          </Badge>
                        )}
                        <Badge
                          variant="outline"
                          className="text-[10px] text-amber-700 border-amber-300"
                        >
                          {c.outcome.status || "pending"}
                        </Badge>
                      </div>
                      <p className="text-sm font-medium leading-snug">
                        {c.problem_features.request}
                      </p>
                      <div className="flex items-center gap-3 mt-2 text-[11px] text-gray-500">
                        <span className="flex items-center gap-1">
                          <GitBranch className="h-3 w-3" />
                          {nodes.length} nodes / {edges.length} edges
                        </span>
                        <span>tools: {tools.join(", ")}</span>
                      </div>
                      <div className="mt-2 flex items-center gap-2">
                        {/* 그래프 편집기 통합은 PR 3 (graph-builder 가 store 인자 받게 일반화) 에서. */}
                        <Button
                          variant="ghost"
                          size="sm"
                          className="ml-auto h-7 text-red-600 hover:text-red-700"
                          onClick={() => handleDelete(cid)}
                        >
                          <Trash2 className="h-3 w-3 mr-1" />
                          삭제
                        </Button>
                      </div>
                      <p className="text-[10px] text-gray-400 mt-1 truncate font-mono">
                        {cid}
                      </p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>

      {/* Dialogs */}
      <SeedGenerateDialog
        open={generateOpen}
        onOpenChange={setGenerateOpen}
        onCompleted={refresh}
      />
      <SeedPromoteDialog
        open={promoteOpen}
        onOpenChange={setPromoteOpen}
        selectedIds={Array.from(selected)}
        onPromoted={() => {
          clearSelection();
          refresh();
        }}
      />

      <Dialog open={pathDialog !== null} onOpenChange={(v) => !v && setPathDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {pathDialog === "export" ? "JSON 으로 Export" : "JSON 에서 Import"}
            </DialogTitle>
            <DialogDescription>
              {pathDialog === "export"
                ? "현재 seed.db 의 모든 케이스를 지정 경로로 내보냅니다."
                : "JSON 파일을 읽어 seed.db 에 추가합니다."}
            </DialogDescription>
          </DialogHeader>
          <Input
            placeholder="/path/to/seeds.json"
            value={pathInput}
            onChange={(e) => setPathInput(e.target.value)}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setPathDialog(null)}>
              취소
            </Button>
            <Button onClick={pathDialog === "export" ? runExport : runImport}>
              실행
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
