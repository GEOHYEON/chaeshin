/**
 * 단일 CBR 케이스 조회·수정·삭제 API.
 * 수정 시 최상위 섹션별로 기존 값을 보존하면서 전달된 필드만 병합한다.
 */
import { NextRequest, NextResponse } from "next/server";
import { readCaseById, writeCase, deleteCase } from "@/lib/case-store";

export async function GET(_req: NextRequest, { params }: { params: Promise<{ caseId: string }> }) {
  const { caseId } = await params;
  const found = readCaseById(caseId);
  if (!found) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json(found);
}

export async function PUT(req: NextRequest, { params }: { params: Promise<{ caseId: string }> }) {
  const { caseId } = await params;
  const body = await req.json();
  const found = readCaseById(caseId);
  if (!found) return NextResponse.json({ error: "Not found" }, { status: 404 });
  // URL의 caseId가 식별자의 정본이므로 body가 metadata.case_id를 바꿀 수 없다.
  const merged = {
    problem_features: { ...found.problem_features, ...(body.problem_features ?? {}) },
    solution: { ...found.solution, ...(body.solution ?? {}) },
    outcome: { ...found.outcome, ...(body.outcome ?? {}) },
    metadata: { ...found.metadata, ...(body.metadata ?? {}), case_id: caseId },
  };
  writeCase(merged);
  return NextResponse.json(merged);
}

export async function DELETE(_req: NextRequest, { params }: { params: Promise<{ caseId: string }> }) {
  const { caseId } = await params;
  const ok = deleteCase(caseId);
  if (!ok) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json({ success: true });
}
