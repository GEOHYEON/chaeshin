import { NextRequest, NextResponse } from "next/server";
import { readEvents } from "@/lib/case-store";

export async function GET(req: NextRequest) {
  const url = req.nextUrl;
  const since = url.searchParams.get("since") || undefined;
  const eventType = url.searchParams.get("event_type") || undefined;
  const limitStr = url.searchParams.get("limit");
  const limit = limitStr ? Math.max(1, Math.min(1000, Number(limitStr))) : 200;

  const events = readEvents({ since, eventType, limit });
  return NextResponse.json({ data: events, total: events.length });
}
