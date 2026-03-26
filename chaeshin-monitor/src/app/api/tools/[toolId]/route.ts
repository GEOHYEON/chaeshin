import { NextRequest, NextResponse } from "next/server";
import { readTools, writeTools } from "@/lib/tool-store";

export async function GET(_req: NextRequest, { params }: { params: Promise<{ toolId: string }> }) {
  const { toolId } = await params;
  const tools = await readTools();
  const found = tools.find((t) => t.id === toolId);
  if (!found) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json(found);
}

export async function PUT(req: NextRequest, { params }: { params: Promise<{ toolId: string }> }) {
  const { toolId } = await params;
  const body = await req.json();
  const tools = await readTools();
  const idx = tools.findIndex((t) => t.id === toolId);
  if (idx === -1) return NextResponse.json({ error: "Not found" }, { status: 404 });

  tools[idx] = { ...tools[idx], ...body, updated_at: new Date().toISOString() };
  await writeTools(tools);
  return NextResponse.json(tools[idx]);
}

export async function DELETE(_req: NextRequest, { params }: { params: Promise<{ toolId: string }> }) {
  const { toolId } = await params;
  const tools = await readTools();
  const filtered = tools.filter((t) => t.id !== toolId);
  if (filtered.length === tools.length) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  await writeTools(filtered);
  return NextResponse.json({ success: true });
}
