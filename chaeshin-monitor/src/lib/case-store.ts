/**
 * Server-side SQLite 접근 레이어.
 *
 * Python 측 chaeshin/storage/sqlite_backend.py 와 동일 스키마를 가진
 * ~/.chaeshin/chaeshin.db 를 읽음.
 *
 * 읽기 전용 인터페이스 + 레거시 호환을 위한 POST (신규 케이스 삽입).
 */
import Database from "better-sqlite3";
import fs from "fs";
import os from "os";
import path from "path";

let _db: Database.Database | null = null;

export function getDbPath(): string {
  return (
    process.env.CHAESHIN_DB_PATH ||
    path.join(os.homedir(), ".chaeshin", "chaeshin.db")
  );
}

function openDb(): Database.Database {
  if (_db) return _db;
  const p = getDbPath();
  fs.mkdirSync(path.dirname(p), { recursive: true });
  _db = new Database(p);
  _db.pragma("journal_mode = WAL");
  _db.pragma("foreign_keys = ON");
  // 스키마 보증 (Python 측이 먼저 생성했다면 no-op)
  _db.exec(`
    CREATE TABLE IF NOT EXISTS cases (
      case_id        TEXT PRIMARY KEY,
      created_at     TEXT NOT NULL,
      updated_at     TEXT NOT NULL,
      layer          TEXT NOT NULL DEFAULT 'L1',
      parent_case_id TEXT NOT NULL DEFAULT '',
      category       TEXT NOT NULL DEFAULT '',
      success        INTEGER NOT NULL DEFAULT 1,
      feedback_count INTEGER NOT NULL DEFAULT 0,
      difficulty     INTEGER NOT NULL DEFAULT 0,
      version        INTEGER NOT NULL DEFAULT 2,
      problem_json   TEXT NOT NULL,
      solution_json  TEXT NOT NULL,
      outcome_json   TEXT NOT NULL,
      metadata_json  TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS events (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      ts            TEXT NOT NULL,
      event_type    TEXT NOT NULL,
      session_id    TEXT NOT NULL DEFAULT '',
      case_ids_json TEXT NOT NULL DEFAULT '[]',
      payload_json  TEXT NOT NULL DEFAULT '{}'
    );
    CREATE TABLE IF NOT EXISTS hierarchy_edges (
      parent_case_id TEXT NOT NULL,
      child_case_id  TEXT NOT NULL,
      parent_node_id TEXT NOT NULL DEFAULT '',
      created_at     TEXT NOT NULL,
      PRIMARY KEY(parent_case_id, child_case_id)
    );
  `);
  return _db;
}

export interface CaseRow {
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
}): CaseRow {
  return {
    problem_features: JSON.parse(row.problem_json),
    solution: JSON.parse(row.solution_json),
    outcome: JSON.parse(row.outcome_json),
    metadata: JSON.parse(row.metadata_json),
  };
}

export function readCases(): CaseRow[] {
  const db = openDb();
  const rows = db
    .prepare(
      "SELECT problem_json, solution_json, outcome_json, metadata_json FROM cases ORDER BY created_at DESC"
    )
    .all() as Array<{
      problem_json: string;
      solution_json: string;
      outcome_json: string;
      metadata_json: string;
    }>;
  return rows.map(rowToCase);
}

export function readCaseById(caseId: string): CaseRow | null {
  const db = openDb();
  const row = db
    .prepare(
      "SELECT problem_json, solution_json, outcome_json, metadata_json FROM cases WHERE case_id = ?"
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

export function deleteCase(caseId: string): boolean {
  const db = openDb();
  const info = db.prepare("DELETE FROM cases WHERE case_id = ?").run(caseId);
  return info.changes > 0;
}

export function appendEvent(
  eventType: string,
  payload: Record<string, unknown>,
  caseIds: string[] = [],
  sessionId = "monitor-ui",
): void {
  const db = openDb();
  db.prepare(
    `INSERT INTO events (ts, event_type, session_id, case_ids_json, payload_json)
     VALUES (?, ?, ?, ?, ?)`,
  ).run(
    new Date().toISOString(),
    eventType,
    sessionId,
    JSON.stringify(caseIds),
    JSON.stringify(payload),
  );
}

export function setVerdict(
  caseId: string,
  status: "success" | "failure",
  note: string,
): CaseRow | null {
  const found = readCaseById(caseId);
  if (!found) return null;
  const outcome = found.outcome as Record<string, unknown>;
  outcome.status = status;
  outcome.success = status === "success";
  outcome.verdict_note = note;
  outcome.verdict_at = new Date().toISOString();
  if (status === "failure" && note && !outcome.error_reason) {
    outcome.error_reason = note;
  }
  writeCase(found);
  appendEvent("verdict", { status, note }, [caseId]);
  return found;
}

export function writeCase(c: CaseRow): void {
  const db = openDb();
  const meta = c.metadata as Record<string, unknown>;
  const caseId = (meta.case_id as string) || crypto.randomUUID();
  const now = new Date().toISOString();
  db.prepare(
    `INSERT INTO cases (
       case_id, created_at, updated_at, layer, parent_case_id, category,
       success, feedback_count, difficulty, version,
       problem_json, solution_json, outcome_json, metadata_json
     ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
     ON CONFLICT(case_id) DO UPDATE SET
       updated_at     = excluded.updated_at,
       layer          = excluded.layer,
       parent_case_id = excluded.parent_case_id,
       category       = excluded.category,
       success        = excluded.success,
       feedback_count = excluded.feedback_count,
       difficulty     = excluded.difficulty,
       version        = excluded.version,
       problem_json   = excluded.problem_json,
       solution_json  = excluded.solution_json,
       outcome_json   = excluded.outcome_json,
       metadata_json  = excluded.metadata_json`
  ).run(
    caseId,
    (meta.created_at as string) || now,
    now,
    (meta.layer as string) || "L1",
    (meta.parent_case_id as string) || "",
    ((c.problem_features as Record<string, unknown>).category as string) || "",
    (c.outcome as Record<string, unknown>).success ? 1 : 0,
    (meta.feedback_count as number) || 0,
    (meta.difficulty as number) || 0,
    (meta.version as number) || 2,
    JSON.stringify(c.problem_features),
    JSON.stringify(c.solution),
    JSON.stringify(c.outcome),
    JSON.stringify(meta),
  );
}

// ── Events ─────────────────────────────────────────────────

export interface EventRow {
  id: number;
  ts: string;
  event_type: string;
  session_id: string;
  case_ids: string[];
  payload: Record<string, unknown>;
}

export function readEvents(opts: {
  since?: string;
  eventType?: string;
  limit?: number;
}): EventRow[] {
  const db = openDb();
  const clauses: string[] = [];
  const params: Array<string | number> = [];
  if (opts.since) {
    clauses.push("ts > ?");
    params.push(opts.since);
  }
  if (opts.eventType) {
    clauses.push("event_type = ?");
    params.push(opts.eventType);
  }
  const where = clauses.length ? `WHERE ${clauses.join(" AND ")}` : "";
  params.push(opts.limit ?? 200);
  const sql = `SELECT id, ts, event_type, session_id, case_ids_json, payload_json
               FROM events ${where} ORDER BY id DESC LIMIT ?`;
  const rows = db.prepare(sql).all(...params) as Array<{
    id: number;
    ts: string;
    event_type: string;
    session_id: string;
    case_ids_json: string;
    payload_json: string;
  }>;
  return rows.map((r) => ({
    id: r.id,
    ts: r.ts,
    event_type: r.event_type,
    session_id: r.session_id,
    case_ids: JSON.parse(r.case_ids_json),
    payload: JSON.parse(r.payload_json),
  }));
}

// ── Hierarchy ──────────────────────────────────────────────

export interface HierarchyEdge {
  parent_case_id: string;
  child_case_id: string;
  parent_node_id: string;
  created_at: string;
}

export function readHierarchyEdges(): HierarchyEdge[] {
  const db = openDb();
  return db
    .prepare(
      "SELECT parent_case_id, child_case_id, parent_node_id, created_at FROM hierarchy_edges"
    )
    .all() as HierarchyEdge[];
}

export interface HierarchyNode {
  case_id: string;
  layer: string;
  depth: number;
  request: string;
  category: string;
  parent_case_id: string;
  parent_node_id: string;
  status: "success" | "failure" | "pending";
  deadline_at: string;
  wait_mode: string;
  feedback_count: number;
}

export function readHierarchyNodes(): HierarchyNode[] {
  const db = openDb();
  const rows = db
    .prepare(
      `SELECT case_id, layer, parent_case_id, category, feedback_count,
              problem_json, outcome_json, metadata_json
       FROM cases`
    )
    .all() as Array<{
      case_id: string;
      layer: string;
      parent_case_id: string;
      category: string;
      feedback_count: number;
      problem_json: string;
      outcome_json: string;
      metadata_json: string;
    }>;
  return rows.map((r) => {
    const pf = JSON.parse(r.problem_json) as { request?: string };
    const out = JSON.parse(r.outcome_json) as {
      status?: string;
      success?: boolean;
    };
    const meta = JSON.parse(r.metadata_json) as {
      depth?: number;
      parent_node_id?: string;
      deadline_at?: string;
      wait_mode?: string;
    };
    const status: "success" | "failure" | "pending" =
      (out.status as "success" | "failure" | "pending") ||
      (out.success ? "success" : "pending");
    return {
      case_id: r.case_id,
      layer: r.layer || "L1",
      depth: meta.depth ?? 0,
      request: pf.request || "",
      category: r.category || "",
      parent_case_id: r.parent_case_id || "",
      parent_node_id: meta.parent_node_id || "",
      status,
      deadline_at: meta.deadline_at || "",
      wait_mode: meta.wait_mode || "deadline",
      feedback_count: r.feedback_count || 0,
    };
  });
}
