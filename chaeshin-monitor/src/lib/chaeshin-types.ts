/**
 * Chaeshin CBR 타입 정의 + Mermaid 변환 유틸.
 *
 * Python의 chaeshin/schema.py와 동일한 구조를 TypeScript로 표현.
 * Weaviate Experience의 inputJson/outputJson/metadataJson을 파싱하여 사용.
 */

// ── Tool Registry ────────────────────────────────────────────

export interface ChaeshinToolParam {
  name: string;
  type: string; // "string" | "number" | "boolean" | "object" | "array"
  description: string;
  required: boolean;
}

export interface ChaeshinTool {
  id: string;
  name: string;
  display_name: string;
  description: string;
  category: string;
  params: ChaeshinToolParam[];
  created_at: string;
  updated_at: string;
}

// ── Tool Graph ───────────────────────────────────────────────

export interface ChaeshinGraphNode {
  id: string;
  tool: string;
  params_hint: Record<string, unknown>;
  note: string;
  input_schema?: Record<string, string>;
  output_schema?: Record<string, string>;
}

export interface ChaeshinGraphEdge {
  from_node: string;
  to_node: string | null;
  condition: string | null;
  action: string | null;
  priority?: number;
  note?: string;
}

export interface ChaeshinToolGraph {
  nodes: ChaeshinGraphNode[];
  edges: ChaeshinGraphEdge[];
  parallel_groups: string[][];
  entry_nodes: string[];
  max_loops: number;
}

// ── CBR Case ─────────────────────────────────────────────────

export interface ChaeshinProblemFeatures {
  request: string;
  category: string;
  keywords: string[];
  constraints: string[];
  context: Record<string, unknown>;
}

export type ChaeshinOutcomeStatus = "success" | "failure" | "pending";

export interface ChaeshinOutcome {
  status?: ChaeshinOutcomeStatus;
  success: boolean;
  result_summary: string;
  tools_executed: number;
  loops_triggered: number;
  total_time_ms: number;
  user_satisfaction: number;
  error_reason: string;
  verdict_note?: string;
  verdict_at?: string;
  details: Record<string, unknown>;
}

export interface ChaeshinCaseMetadata {
  case_id: string;
  created_at: string;
  updated_at: string;
  used_count: number;
  avg_satisfaction: number;
  source: string;
  version: number;
  tags: string[];
  layer?: string;
  depth?: number;
  parent_case_id?: string;
  parent_node_id?: string;
  child_case_ids?: string[];
  wait_mode?: "deadline" | "blocking";
  deadline_at?: string;
  difficulty?: number;
  feedback_count?: number;
  feedback_log?: string[];
}

export interface ChaeshinCase {
  problem_features: ChaeshinProblemFeatures;
  solution: { tool_graph: ChaeshinToolGraph };
  outcome: ChaeshinOutcome;
  metadata: ChaeshinCaseMetadata;
}

// ── Weaviate Experience → ChaeshinCase 변환 ──────────────────

export interface ExperienceForChaeshin {
  id: string;
  userQuery: string;
  isSuccessful: boolean;
  keywords: string[];
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  metadata: Record<string, unknown>;
  createdAt: string;
}

export function experienceToChaeshinCase(
  exp: ExperienceForChaeshin
): ChaeshinCase | null {
  try {
    const pf = exp.input as unknown as ChaeshinProblemFeatures;
    const tg = exp.output as unknown as ChaeshinToolGraph;
    const meta = exp.metadata as {
      outcome?: ChaeshinOutcome;
      metadata?: ChaeshinCaseMetadata;
    };

    return {
      problem_features: {
        request: pf?.request ?? exp.userQuery,
        category: pf?.category ?? "",
        keywords: pf?.keywords ?? exp.keywords ?? [],
        constraints: pf?.constraints ?? [],
        context: pf?.context ?? {},
      },
      solution: {
        tool_graph: {
          nodes: tg?.nodes ?? [],
          edges: tg?.edges ?? [],
          parallel_groups: tg?.parallel_groups ?? [],
          entry_nodes: tg?.entry_nodes ?? [],
          max_loops: tg?.max_loops ?? 3,
        },
      },
      outcome: {
        success: meta?.outcome?.success ?? exp.isSuccessful,
        result_summary: meta?.outcome?.result_summary ?? "",
        tools_executed: meta?.outcome?.tools_executed ?? 0,
        loops_triggered: meta?.outcome?.loops_triggered ?? 0,
        total_time_ms: meta?.outcome?.total_time_ms ?? 0,
        user_satisfaction: meta?.outcome?.user_satisfaction ?? 0,
        error_reason: meta?.outcome?.error_reason ?? "",
        details: meta?.outcome?.details ?? {},
      },
      metadata: {
        case_id: meta?.metadata?.case_id ?? exp.id,
        created_at: meta?.metadata?.created_at ?? exp.createdAt,
        updated_at: meta?.metadata?.updated_at ?? exp.createdAt,
        used_count: meta?.metadata?.used_count ?? 0,
        avg_satisfaction: meta?.metadata?.avg_satisfaction ?? 0,
        source: meta?.metadata?.source ?? "weaviate",
        version: meta?.metadata?.version ?? 1,
        tags: meta?.metadata?.tags ?? [],
      },
    };
  } catch {
    return null;
  }
}

// ── Mermaid 변환 ─────────────────────────────────────────────

function escapeMermaid(text: string): string {
  return text.replace(/"/g, "&quot;").replace(/[[\](){}]/g, "");
}

export function toolGraphToMermaid(graph: ChaeshinToolGraph): string {
  const lines: string[] = ["graph TD"];

  // 노드
  for (const node of graph.nodes) {
    const tool = escapeMermaid(node.tool);
    const note = node.note ? escapeMermaid(node.note) : "";
    const label = note ? `${tool}<br/>${note}` : tool;
    lines.push(`    ${node.id}["${label}"]`);
  }

  // 엣지
  for (const edge of graph.edges) {
    if (edge.to_node) {
      if (edge.condition) {
        const cond = escapeMermaid(edge.condition);
        lines.push(`    ${edge.from_node} -->|${cond}| ${edge.to_node}`);
      } else {
        lines.push(`    ${edge.from_node} --> ${edge.to_node}`);
      }
    } else if (edge.action) {
      const actionId = `${edge.action}_${edge.from_node}`;
      lines.push(`    ${actionId}(("${escapeMermaid(edge.action)}"))`);
      if (edge.condition) {
        lines.push(
          `    ${edge.from_node} -->|${escapeMermaid(edge.condition)}| ${actionId}`
        );
      } else {
        lines.push(`    ${edge.from_node} --> ${actionId}`);
      }
    }
  }

  // 스타일 — entry 노드 강조
  for (const entryId of graph.entry_nodes) {
    lines.push(`    style ${entryId} fill:#059669,color:#fff`);
  }

  return lines.join("\n");
}

// ── Stats 계산 ───────────────────────────────────────────────

export interface ChaeshinStats {
  totalCases: number;
  successCount: number;
  failCount: number;
  successRate: number;
  avgSatisfaction: number;
  totalReuses: number;
  categories: string[];
}

export function computeChaeshinStats(cases: ChaeshinCase[]): ChaeshinStats {
  const successCount = cases.filter((c) => c.outcome.success).length;
  const failCount = cases.length - successCount;
  const totalSat = cases.reduce(
    (sum, c) => sum + c.outcome.user_satisfaction,
    0
  );
  const totalReuses = cases.reduce(
    (sum, c) => sum + c.metadata.used_count,
    0
  );
  const categories = [
    ...new Set(cases.map((c) => c.problem_features.category).filter(Boolean)),
  ];

  return {
    totalCases: cases.length,
    successCount,
    failCount,
    successRate: cases.length > 0 ? successCount / cases.length : 0,
    avgSatisfaction: cases.length > 0 ? totalSat / cases.length : 0,
    totalReuses,
    categories,
  };
}
