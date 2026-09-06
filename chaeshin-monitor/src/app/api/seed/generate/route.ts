/**
 * POST /api/seed/generate
 *
 * Body: { topic: string, tools: string[], count: number, similarityThreshold?: number,
 *         maxAttempts?: number, sampleSeeds?: object[] }
 *
 * `uv run python -m chaeshin.cli.main seed generate ...`를 실행하고 자식 프로세스의
 * stdout JSON 이벤트와 stderr 로그를 하나의 NDJSON 스트림으로 중계한다.
 *
 * 생성에 필요한 OPENAI_API_KEY는 서버 환경에 설정되어 있어야 한다.
 */
import { NextRequest } from "next/server";
import { spawn } from "child_process";
import fs from "fs/promises";
import os from "os";
import path from "path";

import { getSeedDbPath } from "@/lib/seed-store";

export const runtime = "nodejs";
// 긴 LLM 호출 — Vercel-style timeout 회피
export const maxDuration = 600;

interface GenerateBody {
  topic: string;
  tools: string[];
  count: number;
  similarityThreshold?: number;
  maxAttempts?: number;
  sampleSeeds?: unknown[];
}

export async function POST(req: NextRequest) {
  const body = (await req.json()) as GenerateBody;
  if (!body.topic || !body.tools || !body.tools.length || !body.count) {
    return new Response(
      JSON.stringify({ error: "topic, tools, count are required" }),
      { status: 400, headers: { "content-type": "application/json" } },
    );
  }

  const seedDbPath = getSeedDbPath();
  const args = [
    "run",
    "python",
    "-m",
    "chaeshin.cli.main",
    "seed",
    "generate",
    "--topic",
    body.topic,
    "--tools",
    body.tools.join(","),
    "--count",
    String(body.count),
    "--db",
    seedDbPath,
  ];
  if (body.similarityThreshold !== undefined) {
    args.push("--similarity-threshold", String(body.similarityThreshold));
  }
  if (body.maxAttempts !== undefined) {
    args.push("--max-attempts", String(body.maxAttempts));
  }

  // sample_seeds 가 있으면 임시 파일로 떨궈서 --sample-file 로 전달
  let tempSamplePath: string | null = null;
  if (body.sampleSeeds && body.sampleSeeds.length > 0) {
    tempSamplePath = path.join(
      os.tmpdir(),
      `chaeshin-seed-sample-${Date.now()}.json`,
    );
    await fs.writeFile(
      tempSamplePath,
      JSON.stringify(body.sampleSeeds, null, 2),
      "utf-8",
    );
    args.push("--sample-file", tempSamplePath);
  }

  const cwd = pythonProjectCwd();
  let childRef: ReturnType<typeof spawn> | null = null;

  /** 정상 종료와 중단 양쪽에서 임시 샘플 파일을 안전하게 정리한다. */
  const cleanupSample = async () => {
    if (tempSamplePath) {
      try {
        await fs.unlink(tempSamplePath);
      } catch {
        // ignore
      }
    }
  };

  const stream = new ReadableStream({
    start(controller) {
      const enc = new TextEncoder();
      const child = spawn("uv", args, {
        cwd,
        env: { ...process.env },
      });
      childRef = child;

      // 클라이언트가 먼저 연결을 끊어 controller가 닫힌 경우에도 child 종료를 방해하지 않는다.
      const emit = (event: Record<string, unknown>) => {
        try {
          controller.enqueue(enc.encode(JSON.stringify(event) + "\n"));
        } catch {
          // controller already closed (client aborted)
        }
      };

      // chunk 경계가 JSON 한 줄의 경계와 일치하지 않으므로 개행까지 버퍼링한다.
      let stdoutBuf = "";
      child.stdout.on("data", (chunk: Buffer) => {
        stdoutBuf += chunk.toString("utf-8");
        let nlIdx;
        while ((nlIdx = stdoutBuf.indexOf("\n")) !== -1) {
          const line = stdoutBuf.slice(0, nlIdx).trim();
          stdoutBuf = stdoutBuf.slice(nlIdx + 1);
          if (!line) continue;
          // Python emit: 항상 {"event": ...} 형태. structlog 로그는 stderr.
          try {
            const obj = JSON.parse(line);
            emit(obj);
          } catch {
            emit({ event: "log", line });
          }
        }
      });

      child.stderr.on("data", (chunk: Buffer) => {
        const text = chunk.toString("utf-8");
        for (const line of text.split("\n")) {
          if (line.trim()) emit({ event: "log", line });
        }
      });

      child.on("close", async (code) => {
        emit({ event: "done", exit_code: code ?? -1 });
        await cleanupSample();
        try {
          controller.close();
        } catch {
          // already closed
        }
      });

      child.on("error", (err: NodeJS.ErrnoException) => {
        const code = err.code || "";
        const message =
          code === "ENOENT"
            ? "uv 명령을 찾을 수 없습니다. uv 를 설치하거나 PATH 를 확인하세요."
            : String(err);
        emit({ event: "error", code, message });
        try {
          controller.close();
        } catch {
          // already closed
        }
      });
    },
    cancel() {
      // 클라이언트가 fetch abort → child 종료해서 LLM 비용 추가 방지.
      if (childRef && childRef.exitCode === null) {
        try {
          childRef.kill("SIGTERM");
        } catch {
          // ignore
        }
      }
      void cleanupSample();
    },
  });

  // req.signal 이 abort 되면 stream 도 같이 cancel 하도록 연결.
  req.signal.addEventListener("abort", () => {
    if (childRef && childRef.exitCode === null) {
      try {
        childRef.kill("SIGTERM");
      } catch {
        // ignore
      }
    }
  });

  return new Response(stream, {
    headers: {
      "content-type": "application/x-ndjson",
      "cache-control": "no-cache",
    },
  });
}

function pythonProjectCwd(): string {
  // monitor UI 가 chaeshin/chaeshin-monitor 안에 있다고 가정 — 부모 디렉토리.
  return process.env.CHAESHIN_PROJECT_DIR || path.resolve(process.cwd(), "..");
}
