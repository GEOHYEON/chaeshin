/**
 * /api/seed/[caseId] — main /api/chaeshin/[caseId] 와 동일한 응답 모양.
 *
 * GET: case 객체 직접 반환 (data 래핑 없음).
 * PUT: shallow merge — graph-builder 같은 공용 컴포넌트가 store 만 바꿔서 호출 가능.
 * DELETE: { success }.
 */
import { NextRequest, NextResponse } from "next/server";
import {
  deleteSeedCase,
  readSeedCaseById,
  writeSeedCase,
} from "@/lib/seed-store";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ caseId: string }> },
) {
  const { caseId } = await params;
  const c = readSeedCaseById(caseId);
  if (!c) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  return NextResponse.json(c);
}

export async function PUT(
  req: NextRequest,
  { params }: { params: Promise<{ caseId: string }> },
) {
  const { caseId } = await params;
  const body = await req.json();
  const found = readSeedCaseById(caseId);
  if (!found) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  const merged = {
    problem_features: { ...found.problem_features, ...(body.problem_features ?? {}) },
    solution: { ...found.solution, ...(body.solution ?? {}) },
    outcome: { ...found.outcome, ...(body.outcome ?? {}) },
    metadata: { ...found.metadata, ...(body.metadata ?? {}), case_id: caseId },
  };
  writeSeedCase(merged);
  return NextResponse.json(merged);
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ caseId: string }> },
) {
  const { caseId } = await params;
  const ok = deleteSeedCase(caseId);
  if (!ok) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  return NextResponse.json({ success: true });
}
