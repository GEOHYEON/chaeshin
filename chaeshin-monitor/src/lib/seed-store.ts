/**
 * Seed staging DB 접근 레이어 — main chaeshin.db 와 격리된 ~/.chaeshin/seed.db.
 *
 * Python 측 chaeshin/seed/store.py 와 동일한 파일을 공유. m003 이후 schema
 * (layer 컬럼 없는 형태) 로 직접 CREATE — case-store.ts 의 legacy schema 와 분리.
 */
import Database from "better-sqlite3";
import fs from "fs";
import os from "os";
import path from "path";

const _dbCache = new Map<string, Database.Database>();

export function getSeedDbPath(): string {
  return (
    process.env.CHAESHIN_SEED_DB_PATH ||
    path.join(
      process.env.CHAESHIN_STORE_DIR || path.join(os.homedir(), ".chaeshin"),
      "seed.db",
    )
  );
}

function openSeedDb(p?: string): Database.Database {
  const dbPath = p || getSeedDbPath();
  const cached = _dbCache.get(dbPath);
  if (cached) return cached;

  fs.mkdirSync(path.dirname(dbPath), { recursive: true });
  const db = new Database(dbPath);
  db.pragma("journal_mode = WAL");
  db.pragma("foreign_keys = ON");
  db.exec(`
    CREATE TABLE IF NOT EXISTS cases (
      case_id        TEXT PRIMARY KEY,
      created_at     TEXT NOT NULL,
      updated_at     TEXT NOT NULL,
      parent_case_id TEXT NOT NULL DEFAULT '',
      category       TEXT NOT NULL DEFAULT '',
      success        INTEGER NOT NULL DEFAULT 1,
      feedback_count INTEGER NOT NULL DEFAULT 0,
      difficulty     INTEGER NOT NULL DEFAULT 0,
      version        INTEGER NOT NULL DEFAULT 3,
      problem_json   TEXT NOT NULL,
      solution_json  TEXT NOT NULL,
      outcome_json   TEXT NOT NULL,
      metadata_json  TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_cases_parent   ON cases(parent_case_id);
    CREATE INDEX IF NOT EXISTS idx_cases_category ON cases(category);
    CREATE INDEX IF NOT EXISTS idx_cases_success  ON cases(success);
    CREATE TABLE IF NOT EXISTS case_embeddings (
      case_id        TEXT PRIMARY KEY,
      embedding_json TEXT NOT NULL
    );
  `);
  _dbCache.set(dbPath, db);
  return db;
}

export interface SeedCaseRow {
  problem_features: Record<string, unknown>;
  solution: Record<string, unknown>;
  outcome: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

function rowToCase(row: {
  problem_json: string;
  solution_json: string;
  outcome_json: string;
  metadata_json: string;
}): SeedCaseRow {
  return {
    problem_features: JSON.parse(row.problem_json),
    solution: JSON.parse(row.solution_json),
    outcome: JSON.parse(row.outcome_json),
    metadata: JSON.parse(row.metadata_json),
  };
}

export function readSeedCases(opts: { topic?: string } = {}): SeedCaseRow[] {
  const db = openSeedDb();
  const rows = db
    .prepare(
      "SELECT problem_json, solution_json, outcome_json, metadata_json FROM cases ORDER BY created_at DESC",
    )
    .all() as Array<{
      problem_json: string;
      solution_json: string;
      outcome_json: string;
      metadata_json: string;
    }>;
  let out = rows.map(rowToCase);
  if (opts.topic) {
    const t = opts.topic.toLowerCase();
    out = out.filter((c) => {
      const src = String((c.metadata as { source?: string }).source || "").toLowerCase();
      return src.includes(t);
    });
  }
  return out;
}

export function readSeedCaseById(caseId: string): SeedCaseRow | null {
  const db = openSeedDb();
  const row = db
    .prepare(
      "SELECT problem_json, solution_json, outcome_json, metadata_json FROM cases WHERE case_id = ?",
    )
    .get(caseId) as
    | {
        problem_json: string;
        solution_json: string;
        outcome_json: string;
        metadata_json: string;
      }
    | undefined;
  return row ? rowToCase(row) : null;
}

export function writeSeedCase(c: SeedCaseRow): void {
  const db = openSeedDb();
  const meta = c.metadata as Record<string, unknown>;
  const caseId = (meta.case_id as string) || crypto.randomUUID();
  meta.case_id = caseId;
  const now = new Date().toISOString();
  db.prepare(
    `INSERT INTO cases (
       case_id, created_at, updated_at, parent_case_id, category,
       success, feedback_count, difficulty, version,
       problem_json, solution_json, outcome_json, metadata_json
     ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
     ON CONFLICT(case_id) DO UPDATE SET
       updated_at     = excluded.updated_at,
       parent_case_id = excluded.parent_case_id,
       category       = excluded.category,
       success        = excluded.success,
       feedback_count = excluded.feedback_count,
       difficulty     = excluded.difficulty,
       version        = excluded.version,
       problem_json   = excluded.problem_json,
       solution_json  = excluded.solution_json,
       outcome_json   = excluded.outcome_json,
       metadata_json  = excluded.metadata_json`,
  ).run(
    caseId,
    (meta.created_at as string) || now,
    now,
    (meta.parent_case_id as string) || "",
    ((c.problem_features as Record<string, unknown>).category as string) || "",
    (c.outcome as Record<string, unknown>).success ? 1 : 0,
    (meta.feedback_count as number) || 0,
    (meta.difficulty as number) || 0,
    (meta.version as number) || 3,
    JSON.stringify(c.problem_features),
    JSON.stringify(c.solution),
    JSON.stringify(c.outcome),
    JSON.stringify(meta),
  );
}

export function deleteSeedCase(caseId: string): boolean {
  const db = openSeedDb();
  const info = db
    .prepare("DELETE FROM cases WHERE case_id = ?")
    .run(caseId);
  return info.changes > 0;
}

/**
 * Replace the seed case's tool graph. Seeds are flat (no children) so no cascade.
 */
export function reviseSeedGraph(
  caseId: string,
  args: {
    nodes: Array<{
      id?: string;
      tool?: string;
      note?: string;
      params_hint?: Record<string, unknown>;
    }>;
    edges?: Array<{
      from?: string;
      from_node?: string;
      to?: string | null;
      to_node?: string | null;
      condition?: string | null;
    }>;
    reason?: string;
  },
): SeedCaseRow | null {
  const found = readSeedCaseById(caseId);
  if (!found) return null;
  const sol = found.solution as Record<string, unknown>;
  const oldGraph = (sol.tool_graph || {}) as Record<string, unknown>;
  const newNodes = args.nodes.map((n, i) => ({
    id: n.id || `n${i}`,
    tool: n.tool || "unknown",
    params_hint: n.params_hint || {},
    note: n.note || "",
  }));
  const newEdges = (args.edges || []).map((e) => ({
    from_node: e.from_node ?? e.from ?? "",
    to_node: e.to_node ?? e.to ?? null,
    condition: e.condition ?? null,
  }));
  sol.tool_graph = {
    ...oldGraph,
    nodes: newNodes,
    edges: newEdges,
  };
  const meta = found.metadata as Record<string, unknown>;
  meta.updated_at = new Date().toISOString();
  if (args.reason) {
    const log = (meta.feedback_log as string[] | undefined) || [];
    log.push(`[revise] ${args.reason}`);
    meta.feedback_log = log;
  }
  writeSeedCase(found);
  return found;
}

export function countSeedCases(): number {
  const db = openSeedDb();
  const row = db.prepare("SELECT COUNT(*) AS n FROM cases").get() as {
    n: number;
  };
  return row.n;
}
