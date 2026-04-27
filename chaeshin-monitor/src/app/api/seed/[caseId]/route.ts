import { NextRequest, NextResponse } from "next/server";
import {
  deleteSeedCase,
  readSeedCaseById,
  reviseSeedGraph,
  writeSeedCase,
} from "@/lib/seed-store";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ caseId: string }> },
) {
  const { caseId } = await params;
  const c = readSeedCaseById(caseId);
  if (!c) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
  return NextResponse.json({ data: c });
}

export async function PUT(
  req: NextRequest,
  { params }: { params: Promise<{ caseId: string }> },
) {
  const { caseId } = await params;
  const body = await req.json();
  // graph 변경이면 reviseSeedGraph 가, 그 외 metadata 패치는 writeSeedCase 가 처리
  if (body.kind === "graph" && body.nodes) {
    const result = reviseSeedGraph(caseId, {
      nodes: body.nodes,
      edges: body.edges,
      reason: body.reason,
    });
    if (!result) return NextResponse.json({ error: "not found" }, { status: 404 });
    return NextResponse.json({ data: result });
  }
  // 전체 case 객체 받아서 덮어쓰기
  const existing = readSeedCaseById(caseId);
  if (!existing) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
  const meta = (body.metadata ?? existing.metadata) as Record<string, unknown>;
  meta.case_id = caseId;
  writeSeedCase({
    problem_features: body.problem_features ?? existing.problem_features,
    solution: body.solution ?? existing.solution,
    outcome: body.outcome ?? existing.outcome,
    metadata: meta,
  });
  return NextResponse.json({ success: true });
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ caseId: string }> },
) {
  const { caseId } = await params;
  const ok = deleteSeedCase(caseId);
  if (!ok) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
  return NextResponse.json({ success: true });
}
