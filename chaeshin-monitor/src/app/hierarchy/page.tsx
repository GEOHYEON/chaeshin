"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Layers } from "lucide-react";
import { toast } from "sonner";

interface HierarchyNode {
  case_id: string;
  layer: string;
  depth: number;
  request: string;
  category: string;
  parent_case_id: string;
  parent_node_id: string;
  status: "success" | "failure" | "pending";
  deadline_at: string;
  wait_mode: string;
  feedback_count: number;
  graph_summary: {
    node_count: number;
    edge_count: number;
    node_ids: string[];
    tools: string[];
  };
  orphaned: boolean;
}

type Tree = HierarchyNode & { children: Tree[] };

export default function HierarchyPage() {
  const [nodes, setNodes] = useState<HierarchyNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [layerFilter, setLayerFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "pending" | "success" | "failure">(
    "all",
  );

  async function fetchData() {
    setLoading(true);
    try {
      const res = await fetch("/api/hierarchy");
      const json = await res.json();
      setNodes(json.nodes || []);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchData();
  }, []);

  const layers = useMemo(() => {
    const set = new Set<string>();
    for (const n of nodes) set.add(n.layer || "L1");
    return [...set].sort((a, b) => {
      // L3, L2, L1 순 (큰 depth 먼저)
      const na = parseLayer(a);
      const nb = parseLayer(b);
      return nb - na;
    });
  }, [nodes]);

  const counts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const n of nodes) m[n.layer || "L1"] = (m[n.layer || "L1"] || 0) + 1;
    return m;
  }, [nodes]);

  const statusCounts = useMemo(() => {
    const m = { success: 0, failure: 0, pending: 0 };
    for (const n of nodes) m[n.status] = (m[n.status] || 0) + 1;
    return m;
  }, [nodes]);

  const roots = useMemo<Tree[]>(() => {
    const byId = new Map<string, Tree>();
    for (const n of nodes) byId.set(n.case_id, { ...n, children: [] });
    const rootsList: Tree[] = [];
    for (const n of byId.values()) {
      if (n.parent_case_id && byId.has(n.parent_case_id)) {
        byId.get(n.parent_case_id)!.children.push(n);
      } else {
        rootsList.push(n);
      }
    }
    rootsList.sort((a, b) => parseLayer(b.layer) - parseLayer(a.layer));
    return rootsList;
  }, [nodes]);

  const visibleRoots = useMemo(() => {
    let list = roots;
    if (layerFilter !== "all") {
      list = list.filter((r) => containsLayer(r, layerFilter));
    }
    if (statusFilter !== "all") {
      list = list.filter((r) => containsStatus(r, statusFilter));
    }
    return list;
  }, [roots, layerFilter, statusFilter]);

  async function handleVerdict(caseId: string, status: "success" | "failure") {
    const note = window.prompt(
      `${status === "success" ? "성공" : "실패"} verdict 메모 (사용자 원문 인용 권장)`,
      "",
    );
    if (note === null) return; // cancel
    const res = await fetch(`/api/chaeshin/${caseId}/verdict`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, note }),
    });
    if (res.ok) {
      toast.success(`Verdict 기록됨 — ${status}`);
      fetchData();
    } else {
      toast.error("Verdict 저장 실패");
    }
  }

  async function handleRevise(caseId: string) {
    // 현재 그래프를 가져와서 prompt에 채워주고, 사용자가 새 JSON으로 덮어쓰면 revise.
    const cur = await fetch(`/api/chaeshin/${caseId}`).then((r) => r.json()) as {
      solution?: { tool_graph?: { nodes?: unknown[]; edges?: unknown[] } };
    };
    const currentGraph = {
      nodes: cur?.solution?.tool_graph?.nodes ?? [],
      edges: cur?.solution?.tool_graph?.edges ?? [],
    };
    const initial = JSON.stringify(currentGraph, null, 2);
    const next = window.prompt(
      "새 그래프 JSON (nodes/edges). 제거된 노드에 매달린 자식은 자동으로 pending 회귀.",
      initial,
    );
    if (next === null) return;
    let parsed: { nodes?: unknown[]; edges?: unknown[] };
    try {
      parsed = JSON.parse(next) as { nodes?: unknown[]; edges?: unknown[] };
    } catch (e) {
      toast.error(`JSON 파싱 실패: ${(e as Error).message}`);
      return;
    }
    const reason = window.prompt("수정 사유 (이유 한 줄)", "") || "";
    const res = await fetch(`/api/chaeshin/${caseId}/revise`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ graph: parsed, reason, cascade: true }),
    });
    if (!res.ok) {
      toast.error("Revise 저장 실패");
      return;
    }
    const result = (await res.json()) as {
      added_nodes?: string[];
      removed_nodes?: string[];
      orphaned_children?: string[];
    };
    const orphans = result.orphaned_children?.length ?? 0;
    toast.success(
      `Revise 완료 — 추가 ${result.added_nodes?.length ?? 0} · 제거 ${result.removed_nodes?.length ?? 0}` +
        (orphans > 0 ? ` · 고아 ${orphans} (검토 필요)` : ""),
    );
    fetchData();
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="sticky top-0 z-30 border-b bg-white">
        <div className="flex items-center gap-3 px-6 h-14 max-w-7xl mx-auto">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-[hsl(var(--primary))] text-white">
            <Layers className="h-4 w-4" />
          </div>
          <div>
            <h1 className="text-base font-semibold tracking-tight">Hierarchy</h1>
            <p className="text-[11px] text-gray-400 leading-none">
              Graphs all the way down — 모든 노드는 자기 자신도 그래프로 펼쳐질 수 있다
            </p>
          </div>
          <nav className="ml-auto flex items-center gap-4 text-sm">
            <Link href="/" className="text-gray-500 hover:text-gray-900">
              Cases
            </Link>
            <Link href="/events" className="text-gray-500 hover:text-gray-900">
              Events
            </Link>
            <Link href="/hierarchy" className="font-medium text-gray-900">
              Hierarchy
            </Link>
          </nav>
        </div>
      </header>

      <main className="p-6 max-w-7xl mx-auto space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[10px] text-gray-400 mr-1">LAYER</span>
          <FilterBtn
            active={layerFilter === "all"}
            onClick={() => setLayerFilter("all")}
            label="all"
          />
          {layers.map((l) => (
            <FilterBtn
              key={l}
              active={layerFilter === l}
              onClick={() => setLayerFilter(l)}
              label={`${l} (${counts[l] || 0})`}
            />
          ))}
          <span className="text-[10px] text-gray-400 ml-4 mr-1">STATUS</span>
          <FilterBtn
            active={statusFilter === "all"}
            onClick={() => setStatusFilter("all")}
            label="all"
          />
          <FilterBtn
            active={statusFilter === "pending"}
            onClick={() => setStatusFilter("pending")}
            label={`pending (${statusCounts.pending})`}
            tone="amber"
          />
          <FilterBtn
            active={statusFilter === "success"}
            onClick={() => setStatusFilter("success")}
            label={`success (${statusCounts.success})`}
            tone="green"
          />
          <FilterBtn
            active={statusFilter === "failure"}
            onClick={() => setStatusFilter("failure")}
            label={`failure (${statusCounts.failure})`}
            tone="red"
          />
          <span className="ml-auto text-xs text-gray-400">
            {loading ? "loading…" : `${nodes.length} cases · ${roots.length} roots`}
          </span>
        </div>

        <div className="rounded-lg border bg-white p-4">
          {visibleRoots.length === 0 ? (
            <div className="p-8 text-center text-sm text-gray-400">
              표시할 케이스가 없습니다.
            </div>
          ) : (
            <ul className="space-y-1">
              {visibleRoots.map((r) => (
                <TreeNode
                  key={r.case_id}
                  node={r}
                  depth={0}
                  onVerdict={handleVerdict}
                  onRevise={handleRevise}
                />
              ))}
            </ul>
          )}
        </div>
      </main>
    </div>
  );
}

function FilterBtn({
  active,
  onClick,
  label,
  tone = "neutral",
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  tone?: "neutral" | "green" | "red" | "amber";
}) {
  const activeCls =
    tone === "green"
      ? "bg-green-600 text-white border-green-600"
      : tone === "red"
        ? "bg-red-600 text-white border-red-600"
        : tone === "amber"
          ? "bg-amber-500 text-white border-amber-500"
          : "bg-gray-900 text-white border-gray-900";
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1 rounded-full text-xs border transition ${
        active ? activeCls : "bg-white text-gray-600 border-gray-200 hover:border-gray-400"
      }`}
    >
      {label}
    </button>
  );
}

function parseLayer(l: string): number {
  if (l && l.startsWith("L") && /^\d+$/.test(l.slice(1))) return Number(l.slice(1));
  return 1;
}

function containsLayer(node: Tree, layer: string): boolean {
  if ((node.layer || "L1") === layer) return true;
  return node.children.some((c) => containsLayer(c, layer));
}

function containsStatus(node: Tree, status: "success" | "failure" | "pending"): boolean {
  if (node.status === status) return true;
  return node.children.some((c) => containsStatus(c, status));
}

function TreeNode({
  node,
  depth,
  onVerdict,
  onRevise,
}: {
  node: Tree;
  depth: number;
  onVerdict: (caseId: string, status: "success" | "failure") => void;
  onRevise: (caseId: string) => void;
}) {
  const [open, setOpen] = useState(depth < 1);
  const hasChildren = node.children.length > 0;
  const layer = node.layer || "L1";
  const overdue =
    node.status === "pending" &&
    node.deadline_at &&
    new Date(node.deadline_at).getTime() < Date.now();

  return (
    <li>
      <div
        className="group flex items-center gap-2 py-1.5 px-2 rounded hover:bg-gray-50"
        style={{ paddingLeft: `${depth * 1.25 + 0.5}rem` }}
      >
        <button
          onClick={() => hasChildren && setOpen(!open)}
          className={`w-4 text-xs ${hasChildren ? "text-gray-500" : "text-transparent"}`}
        >
          {hasChildren ? (open ? "▾" : "▸") : "·"}
        </button>
        <span
          className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${layerColor(layer)}`}
        >
          {layer}
        </span>
        <StatusBadge status={node.status} overdue={!!overdue} />
        {node.orphaned && (
          <span
            className="text-[10px] px-1.5 py-0.5 rounded bg-rose-100 text-rose-700 shrink-0"
            title="상위 그래프의 anchor 노드가 revise로 제거됨 — 검토/재연결 필요"
          >
            orphan
          </span>
        )}
        <span className="text-sm text-gray-800 truncate flex-1">{node.request}</span>
        {node.parent_node_id && (
          <span
            className="text-[10px] font-mono text-gray-400 shrink-0"
            title={`상위 그래프의 '${node.parent_node_id}' 노드를 펼친 결과`}
          >
            ↱{node.parent_node_id}
          </span>
        )}
        <GraphSummary summary={node.graph_summary} />
        <div className="opacity-0 group-hover:opacity-100 transition flex gap-1 shrink-0">
          {node.status === "pending" && (
            <>
              <button
                onClick={() => onVerdict(node.case_id, "success")}
                className="text-[10px] px-1.5 py-0.5 rounded bg-green-100 text-green-700 hover:bg-green-200"
              >
                ✓ 성공
              </button>
              <button
                onClick={() => onVerdict(node.case_id, "failure")}
                className="text-[10px] px-1.5 py-0.5 rounded bg-red-100 text-red-700 hover:bg-red-200"
              >
                ✗ 실패
              </button>
            </>
          )}
          <button
            onClick={() => onRevise(node.case_id)}
            className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-700 hover:bg-indigo-200"
            title="이 케이스의 그래프 수정 — 사라진 노드의 자식은 pending 회귀"
          >
            ✎ revise
          </button>
        </div>
        {node.category && (
          <span className="text-[10px] text-gray-400 shrink-0">{node.category}</span>
        )}
        {node.feedback_count > 0 && (
          <span className="text-[10px] text-amber-600 shrink-0">★{node.feedback_count}</span>
        )}
        <span className="text-[10px] font-mono text-gray-300 shrink-0">
          {node.case_id.slice(0, 8)}
        </span>
      </div>
      {hasChildren && open && (
        <ul>
          {node.children.map((c) => (
            <TreeNode
              key={c.case_id}
              node={c}
              depth={depth + 1}
              onVerdict={onVerdict}
              onRevise={onRevise}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

function GraphSummary({
  summary,
}: {
  summary: HierarchyNode["graph_summary"];
}) {
  if (!summary || summary.node_count === 0) return null;
  const tip =
    `graph: ${summary.node_count} node${summary.node_count > 1 ? "s" : ""}, ` +
    `${summary.edge_count} edge${summary.edge_count > 1 ? "s" : ""}\n` +
    (summary.node_ids.length ? `ids: ${summary.node_ids.join(", ")}\n` : "") +
    (summary.tools.length ? `tools: ${summary.tools.join(", ")}` : "");
  return (
    <span
      className="text-[10px] font-mono text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded shrink-0 cursor-help"
      title={tip}
    >
      ⊞{summary.node_count}·{summary.edge_count}
    </span>
  );
}

function StatusBadge({
  status,
  overdue,
}: {
  status: "success" | "failure" | "pending";
  overdue: boolean;
}) {
  if (status === "success") {
    return <span className="text-[10px] text-green-600 shrink-0">✓</span>;
  }
  if (status === "failure") {
    return <span className="text-[10px] text-red-600 shrink-0">✗</span>;
  }
  return (
    <span
      className={`text-[10px] px-1 rounded shrink-0 ${
        overdue ? "bg-amber-200 text-amber-900" : "bg-amber-100 text-amber-700"
      }`}
      title={overdue ? "deadline 경과 — 중간 상태 유지" : "사용자 verdict 대기 중"}
    >
      ⋯
    </span>
  );
}

function layerColor(l: string): string {
  const n = parseLayer(l);
  if (n >= 3) return "bg-purple-100 text-purple-700";
  if (n === 2) return "bg-blue-100 text-blue-700";
  return "bg-gray-100 text-gray-600";
}
