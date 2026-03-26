import { NextResponse } from "next/server";
import { readCases } from "@/lib/case-store";

export async function GET() {
  const cases = (await readCases()) as Record<string, unknown>[];

  let successCount = 0;
  let totalSat = 0;
  let totalReuses = 0;
  const categories = new Set<string>();

  for (const c of cases) {
    const out = c.outcome as Record<string, unknown>;
    const meta = c.metadata as Record<string, unknown>;
    const pf = c.problem_features as Record<string, unknown>;

    if (out?.success) successCount++;
    totalSat += Number(out?.user_satisfaction ?? 0);
    totalReuses += Number(meta?.used_count ?? 0);
    if (pf?.category) categories.add(String(pf.category));
  }

  return NextResponse.json({
    totalCases: cases.length,
    successCount,
    failCount: cases.length - successCount,
    successRate: cases.length > 0 ? successCount / cases.length : 0,
    avgSatisfaction: cases.length > 0 ? totalSat / cases.length : 0,
    totalReuses,
    categories: [...categories],
  });
}
