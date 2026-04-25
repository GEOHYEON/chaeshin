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
