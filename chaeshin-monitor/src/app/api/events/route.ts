/** 이벤트 타임라인을 시간·종류로 필터링해 최신순으로 반환한다. */
import { NextRequest, NextResponse } from "next/server";
import { readEvents } from "@/lib/case-store";

export async function GET(req: NextRequest) {
  const url = req.nextUrl;
  const since = url.searchParams.get("since") || undefined;
  const eventType = url.searchParams.get("event_type") || undefined;
  const limitStr = url.searchParams.get("limit");
  // 한 번의 모니터 요청이 이벤트 테이블 전체를 읽지 않도록 상한을 둔다.
  const limit = limitStr ? Math.max(1, Math.min(1000, Number(limitStr))) : 200;

  const events = readEvents({ since, eventType, limit });
  return NextResponse.json({ data: events, total: events.length });
}
