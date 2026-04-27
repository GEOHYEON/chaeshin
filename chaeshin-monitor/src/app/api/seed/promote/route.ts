/**
 * POST /api/seed/promote
 * Body: { caseIds: string[], force?: boolean }
 * → spawn `chaeshin seed promote --ids ID1,ID2 [--force]`
 *   id 발급 / promoted_from 마커 / idempotency 는 Python promoter 가 처리.
 */
import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import path from "path";

import { getSeedDbPath } from "@/lib/seed-store";

export const runtime = "nodejs";
export const maxDuration = 120;

interface PromoteBody {
  caseIds: string[];
  force?: boolean;
}

export async function POST(req: NextRequest) {
  const body = (await req.json()) as PromoteBody;
  if (!Array.isArray(body.caseIds) || body.caseIds.length === 0) {
    return NextResponse.json({ error: "caseIds is required" }, { status: 400 });
  }

  const args = [
    "run",
    "python",
    "-m",
    "chaeshin.cli.main",
    "seed",
    "promote",
    "--ids",
    body.caseIds.join(","),
    "--seed-db",
    getSeedDbPath(),
  ];
  if (body.force) args.push("--force");

  const cwd = process.env.CHAESHIN_PROJECT_DIR || path.resolve(process.cwd(), "..");

  return new Promise<Response>((resolve) => {
    const child = spawn("uv", args, { cwd, env: { ...process.env } });
    let stdout = "";
    let stderr = "";
    let settled = false;
    const finish = (res: Response) => {
      if (settled) return;
      settled = true;
      resolve(res);
    };
    child.stdout.on("data", (c) => {
      stdout += c.toString("utf-8");
    });
    child.stderr.on("data", (c) => {
      stderr += c.toString("utf-8");
    });
    child.on("close", (code) => {
      // Python 출력에서 마지막 JSON 객체 추출 (structlog 로그 섞일 수 있음)
      const start = stdout.lastIndexOf("{");
      let payload: unknown = null;
      if (start !== -1) {
        try {
          payload = JSON.parse(stdout.slice(start));
        } catch {
          payload = null;
        }
      }
      finish(
        NextResponse.json({
          exit_code: code ?? -1,
          payload,
          raw_stdout: stdout,
          raw_stderr: stderr,
        }),
      );
    });
    child.on("error", (err: NodeJS.ErrnoException) => {
      const code = err.code || "";
      const message =
        code === "ENOENT"
          ? "uv 명령을 찾을 수 없습니다. uv 를 설치하거나 PATH 를 확인하세요."
          : String(err);
      finish(
        NextResponse.json(
          { error: message, code, exit_code: -1 },
          { status: 500 },
        ),
      );
    });
  });
}
