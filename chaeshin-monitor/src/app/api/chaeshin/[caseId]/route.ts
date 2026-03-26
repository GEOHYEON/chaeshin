import { NextRequest, NextResponse } from "next/server";
import { readCases, writeCases } from "@/lib/case-store";

type CaseRecord = Record<string, unknown>;

function getCaseId(c: CaseRecord): string {
  const meta = c.metadata as Record<string, unknown>;
  return String(meta?.case_id ?? "");
}

export async function GET(_req: NextRequest, { params }: { params: Promise<{ caseId: string }> }) {
  const { caseId } = await params;
  const cases = (await readCases()) as CaseRecord[];
  const found = cases.find((c) => getCaseId(c) === caseId);
  if (!found) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json(found);
}

export async function PUT(req: NextRequest, { params }: { params: Promise<{ caseId: string }> }) {
  const { caseId } = await params;
  const body = await req.json();
  const cases = (await readCases()) as CaseRecord[];
  const idx = cases.findIndex((c) => getCaseId(c) === caseId);
  if (idx === -1) return NextResponse.json({ error: "Not found" }, { status: 404 });

  // Merge updates
  cases[idx] = { ...cases[idx], ...body };
  await writeCases(cases);
  return NextResponse.json(cases[idx]);
}

export async function DELETE(_req: NextRequest, { params }: { params: Promise<{ caseId: string }> }) {
  const { caseId } = await params;
  const cases = (await readCases()) as CaseRecord[];
  const filtered = cases.filter((c) => getCaseId(c) !== caseId);
  if (filtered.length === cases.length) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  await writeCases(filtered);
  return NextResponse.json({ success: true });
}
