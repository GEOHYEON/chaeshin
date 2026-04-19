import { NextRequest, NextResponse } from "next/server";
import { readCases, writeCase } from "@/lib/case-store";

export async function GET(req: NextRequest) {
  const cases = readCases();
  const url = req.nextUrl;
  const category = url.searchParams.get("category");
  const success = url.searchParams.get("success");
  const search = url.searchParams.get("search");

  let filtered = cases as unknown as Record<string, unknown>[];

  if (category) {
    filtered = filtered.filter((c) => {
      const pf = c.problem_features as Record<string, unknown>;
      return pf?.category === category;
    });
  }
  if (success === "true" || success === "false") {
    const val = success === "true";
    filtered = filtered.filter((c) => {
      const out = c.outcome as Record<string, unknown>;
      return out?.success === val;
    });
  }
  if (search) {
    const q = search.toLowerCase();
    filtered = filtered.filter((c) => {
      const pf = c.problem_features as Record<string, unknown>;
      return (
        String(pf?.request ?? "").toLowerCase().includes(q) ||
        String(pf?.category ?? "").toLowerCase().includes(q)
      );
    });
  }

  return NextResponse.json({ data: filtered, total: filtered.length });
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  writeCase(body);
  return NextResponse.json({ success: true });
}
