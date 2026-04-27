/**
 * POST /api/seed/export
 * Body: { path: string }
 * → seed.db 의 모든 케이스를 JSON 파일로 내보낸다 (서버 파일시스템에 작성).
 */
import { NextRequest, NextResponse } from "next/server";
import fs from "fs/promises";
import path from "path";

import { readSeedCases } from "@/lib/seed-store";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const outPath = (body?.path as string) || "";
  if (!outPath) {
    return NextResponse.json({ error: "path is required" }, { status: 400 });
  }

  const cases = readSeedCases();
  await fs.mkdir(path.dirname(outPath), { recursive: true });
  await fs.writeFile(outPath, JSON.stringify(cases, null, 2), "utf-8");
  return NextResponse.json({ success: true, path: outPath, count: cases.length });
}
