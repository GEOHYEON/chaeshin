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
