import { NextRequest, NextResponse } from "next/server";
import { readTools, writeTools } from "@/lib/tool-store";

export async function GET(req: NextRequest) {
  const tools = await readTools();
  const category = req.nextUrl.searchParams.get("category");

  const filtered = category
    ? tools.filter((t) => t.category === category)
    : tools;

  return NextResponse.json({ data: filtered, total: filtered.length });
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const tools = await readTools();

  body.created_at = body.created_at || new Date().toISOString();
  body.updated_at = new Date().toISOString();

  tools.push(body);
  await writeTools(tools);
  return NextResponse.json({ success: true, total: tools.length });
}
