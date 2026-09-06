/** 케이스 계층을 화면에서 조립할 수 있도록 노드와 명시적 엣지를 함께 반환한다. */
import { NextResponse } from "next/server";
import { readHierarchyNodes, readHierarchyEdges } from "@/lib/case-store";

export async function GET() {
  const nodes = readHierarchyNodes();
  const edges = readHierarchyEdges();
  return NextResponse.json({ nodes, edges });
}
