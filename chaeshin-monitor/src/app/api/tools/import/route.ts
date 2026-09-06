import { NextRequest, NextResponse } from "next/server";
import { readTools, writeTools } from "@/lib/tool-store";
import type { ChaeshinTool } from "@/lib/chaeshin-types";
import fs from "fs/promises";
import path from "path";
import os from "os";
import { spawn } from "child_process";

/**
 * POST /api/tools/import?source=claude-code|openclaw
 *
 * Claude Code: ~/.claude.json → MCP 서버별 프로세스 실행 → tools/list
 * OpenClaw: ~/.openclaw/workspace/skills/ → SKILL.md 읽기
 */

// ── stdio 기반 MCP tools/list ─────────────────────────────────

/**
 * MCP 서버 프로세스와 짧은 세션을 열어 공개 도구 목록을 가져온다.
 * 외부 서버 하나의 실패가 전체 import를 막지 않도록 빈 배열로 수렴한다.
 */
function getMcpTools(command: string, args: string[]): Promise<Array<{ name: string; description: string; inputSchema?: Record<string, unknown> }>> {
  return new Promise((resolve) => {
    const proc = spawn(command, args, { stdio: ["pipe", "pipe", "pipe"], timeout: 10000 });
    let stdout = "";

    proc.stdout.on("data", (d: Buffer) => { stdout += d.toString(); });

    // MCP 세션 수립을 위해 initialize를 먼저 전송한다.
    const initMsg = JSON.stringify({ jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: "2024-11-05", capabilities: {}, clientInfo: { name: "chaeshin-monitor", version: "1.0" } } });
    proc.stdin.write(`Content-Length: ${Buffer.byteLength(initMsg)}\r\n\r\n${initMsg}`);

    // initialize 응답을 기다릴 별도 상태기가 없어 짧은 유예 뒤 tools/list를 보낸다.
    setTimeout(() => {
      const listMsg = JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/list", params: {} });
      proc.stdin.write(`Content-Length: ${Buffer.byteLength(listMsg)}\r\n\r\n${listMsg}`);
    }, 500);

    // 응답 수집 시간을 제한해 응답하지 않는 MCP 서버에 매달리지 않는다.
    setTimeout(() => {
      proc.kill();

      // 일부 서버가 Content-Length framing 없이 출력하는 응답도 우선 탐색한다.
      const tools: Array<{ name: string; description: string; inputSchema?: Record<string, unknown> }> = [];
      const matches = stdout.match(/\{[^{}]*"tools"\s*:\s*\[[\s\S]*?\]\s*\}/g);
      if (matches) {
        for (const m of matches) {
          try {
            const parsed = JSON.parse(m);
            if (parsed.tools && Array.isArray(parsed.tools)) {
              tools.push(...parsed.tools);
            }
          } catch { /* skip */ }
        }
      }

      // 표준 Content-Length framing 응답은 두 번째 경로에서 파싱한다.
      if (tools.length === 0) {
        const jsonBlocks = stdout.split(/Content-Length: \d+\r?\n\r?\n/).filter(Boolean);
        for (const block of jsonBlocks) {
          try {
            const parsed = JSON.parse(block.trim());
            if (parsed.result?.tools) {
              tools.push(...parsed.result.tools);
            }
          } catch { /* skip */ }
        }
      }

      resolve(tools);
    }, 3000);

    proc.on("error", () => resolve([]));
  });
}

// ── Claude Code 가져오기 ──────────────────────────────────────

/** 로컬 Claude Code 설정의 MCP 서버들을 도구 레지스트리 형식으로 변환한다. */
async function importFromClaudeCode(): Promise<ChaeshinTool[]> {
  const imported: ChaeshinTool[] = [];

  // 전역 설정과 세부 설정 양쪽에 흩어진 MCP 서버 구성을 합친다.
  const configPaths = [
    path.join(os.homedir(), ".claude.json"),
    path.join(os.homedir(), ".claude", "settings.json"),
  ];

  let mcpServers: Record<string, { command: string; args?: string[] }> = {};

  for (const configPath of configPaths) {
    try {
      const raw = await fs.readFile(configPath, "utf-8");
      const config = JSON.parse(raw);
      if (config.mcpServers) {
        mcpServers = { ...mcpServers, ...config.mcpServers };
      }
    } catch { /* file not found */ }
  }

  // 서버별 오류는 격리해 응답 가능한 서버의 도구만 가져온다.
  for (const [serverName, serverConfig] of Object.entries(mcpServers)) {
    if (serverName === "chaeshin") continue; // Skip self

    try {
      const mcpTools = await getMcpTools(
        serverConfig.command,
        serverConfig.args || []
      );

      for (const tool of mcpTools) {
        // JSON Schema의 properties/required를 화면용 파라미터 목록으로 평탄화한다.
        const params: ChaeshinTool["params"] = [];
        const schema = tool.inputSchema;
        if (schema && typeof schema === "object" && "properties" in schema) {
          const props = schema.properties as Record<string, { type?: string; description?: string }>;
          const required = (schema as { required?: string[] }).required || [];
          for (const [pName, pDef] of Object.entries(props)) {
            params.push({
              name: pName,
              type: pDef.type || "string",
              description: pDef.description || "",
              required: required.includes(pName),
            });
          }
        }

        imported.push({
          id: `${serverName}_${tool.name}`,
          name: tool.name,
          display_name: tool.name,
          description: tool.description || "",
          category: `Claude Code: ${serverName}`,
          params,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
      }
    } catch { /* server failed to respond */ }
  }

  return imported;
}

// ── OpenClaw 가져오기 ─────────────────────────────────────────

/** OpenClaw skill 디렉터리의 frontmatter를 도구 레지스트리 형식으로 변환한다. */
async function importFromOpenClaw(): Promise<ChaeshinTool[]> {
  const imported: ChaeshinTool[] = [];
  const skillsDir = path.join(os.homedir(), ".openclaw", "workspace", "skills");

  try {
    const entries = await fs.readdir(skillsDir, { withFileTypes: true });

    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      if (entry.name === "chaeshin") continue; // Skip self

      const skillPath = path.join(skillsDir, entry.name, "SKILL.md");
      try {
        const content = await fs.readFile(skillPath, "utf-8");

        // 전체 Markdown 파서는 사용하지 않고 필요한 frontmatter 필드만 읽는다.
        const fmMatch = content.match(/^---\s*\n([\s\S]*?)\n---/);
        let name = entry.name;
        let description = "";

        if (fmMatch) {
          const fm = fmMatch[1];
          const nameMatch = fm.match(/name:\s*(.+)/);
          const descMatch = fm.match(/description:\s*"?(.+?)"?\s*$/m);
          if (nameMatch) name = nameMatch[1].trim();
          if (descMatch) description = descMatch[1].trim();
        }

        imported.push({
          id: `openclaw_${entry.name}`,
          name: entry.name,
          display_name: name,
          description,
          category: "OpenClaw Skill",
          params: [],
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
      } catch { /* SKILL.md not found */ }
    }
  } catch { /* skills dir not found */ }

  return imported;
}

// ── 요청 처리 ─────────────────────────────────────────────────

export async function POST(req: NextRequest) {
  const source = req.nextUrl.searchParams.get("source");

  let imported: ChaeshinTool[] = [];

  if (source === "claude-code") {
    imported = await importFromClaudeCode();
  } else if (source === "openclaw") {
    imported = await importFromOpenClaw();
  } else {
    return NextResponse.json({ error: "source required: claude-code or openclaw" }, { status: 400 });
  }

  if (imported.length === 0) {
    return NextResponse.json({ imported: 0, message: "가져올 도구가 없습니다" });
  }

  // 기존 id는 덮어쓰지 않아 사용자가 편집한 도구 정의를 보존한다.
  const existing = await readTools();
  const existingIds = new Set(existing.map((t) => t.id));
  const newTools = imported.filter((t) => !existingIds.has(t.id));

  if (newTools.length > 0) {
    await writeTools([...existing, ...newTools]);
  }

  return NextResponse.json({
    imported: newTools.length,
    skipped: imported.length - newTools.length,
    total: existing.length + newTools.length,
  });
}
