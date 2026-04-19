import { NextResponse } from "next/server";
import { readHierarchyNodes, readHierarchyEdges } from "@/lib/case-store";

export async function GET() {
  const nodes = readHierarchyNodes();
  const edges = readHierarchyEdges();
  return NextResponse.json({ nodes, edges });
}
