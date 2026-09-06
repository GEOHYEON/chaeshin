/**
 * 단일 케이스의 Tool Graph를 교체하고 필요하면 하위 케이스 상태를 연쇄 갱신한다.
 * cascade는 명시적으로 false를 전달하지 않는 한 활성화된다.
 */
import { NextRequest, NextResponse } from "next/server";
import { reviseCaseGraph } from "@/lib/case-store";

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ caseId: string }> },
) {
  const { caseId } = await params;
  const body = (await req.json()) as {
    graph?: { nodes?: unknown[]; edges?: unknown[] };
    reason?: string;
    cascade?: boolean;
  };
  const nodes = (body.graph?.nodes || []) as Array<{
    id?: string;
    tool?: string;
    note?: string;
    params_hint?: Record<string, unknown>;
  }>;
  if (!Array.isArray(nodes) || nodes.length === 0) {
    return NextResponse.json(
      { error: "graph.nodes is required and must be a non-empty array" },
      { status: 400 },
    );
  }
  const edges = (body.graph?.edges || []) as Array<{
    from?: string;
    from_node?: string;
    to?: string | null;
    to_node?: string | null;
    condition?: string;
  }>;

  // 그래프 정규화와 고아 하위 케이스 판정은 저장소 계층에서 한 번에 처리한다.
  const result = reviseCaseGraph(caseId, {
    nodes,
    edges,
    reason: body.reason || "",
    cascade: body.cascade !== false,
  });
  if (!result) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  return NextResponse.json({ success: true, ...result });
}
