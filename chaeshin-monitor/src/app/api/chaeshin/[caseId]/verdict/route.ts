import { NextRequest, NextResponse } from "next/server";
import { setVerdict } from "@/lib/case-store";

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ caseId: string }> },
) {
  const { caseId } = await params;
  const body = (await req.json()) as { status?: string; note?: string };
  const status = body.status;
  if (status !== "success" && status !== "failure") {
    return NextResponse.json(
      { error: "status must be 'success' or 'failure'" },
      { status: 400 },
    );
  }
  const updated = setVerdict(caseId, status, body.note || "");
  if (!updated) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  return NextResponse.json({ success: true, case: updated });
}
