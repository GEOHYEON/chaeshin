/** seed staging DB의 케이스 목록 조회·생성 API. */
import { NextRequest, NextResponse } from "next/server";
import { readSeedCases, writeSeedCase } from "@/lib/seed-store";

export async function GET(req: NextRequest) {
  const topic = req.nextUrl.searchParams.get("topic") || undefined;
  const cases = readSeedCases({ topic });
  return NextResponse.json({ data: cases, total: cases.length });
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  writeSeedCase(body);
  return NextResponse.json({ success: true });
}
