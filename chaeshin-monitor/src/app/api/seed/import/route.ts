/**
 * POST /api/seed/import
 * Body: { path: string }
 * → JSON 파일을 읽어 seed.db 에 케이스를 삽입한다.
 */
import { NextRequest, NextResponse } from "next/server";
import fs from "fs/promises";

import { writeSeedCase, type SeedCaseRow } from "@/lib/seed-store";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const inPath = (body?.path as string) || "";
  if (!inPath) {
    return NextResponse.json({ error: "path is required" }, { status: 400 });
  }
  const raw = await fs.readFile(inPath, "utf-8");
  const parsed = JSON.parse(raw);
  const list = Array.isArray(parsed) ? parsed : parsed?.data;
  if (!Array.isArray(list)) {
    return NextResponse.json(
      { error: "file must contain a JSON array of cases" },
      { status: 400 },
    );
  }
  let added = 0;
  for (const c of list as SeedCaseRow[]) {
    writeSeedCase(c);
    added += 1;
  }
  return NextResponse.json({ success: true, added });
}
