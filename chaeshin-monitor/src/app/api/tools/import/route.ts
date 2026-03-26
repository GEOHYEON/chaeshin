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
 * Claude Code: ~/.claude.json → MCP servers → spawn each → tools/list
 * OpenClaw: ~/.openclaw/workspace/skills/ → read SKILL.md files
 */

// ── MCP tools/list via stdio ──────────────────────────────────

function getMcpTools(command: string, args: string[]): Promise<Array<{ name: string; description: string; inputSchema?: Record<string, unknown> }>> {
  return new Promise((resolve) => {
    const proc = spawn(command, args, { stdio: ["pipe", "pipe", "pipe"], timeout: 10000 });
    let stdout = "";

    proc.stdout.on("data", (d: Buffer) => { stdout += d.toString(); });

    // Send initialize
    const initMsg = JSON.stringify({ jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: "2024-11-05", capabilities: {}, clientInfo: { name: "chaeshin-monitor", version: "1.0" } } });
    proc.stdin.write(`Content-Length: ${Buffer.byteLength(initMsg)}\r\n\r\n${initMsg}`);

    // Send tools/list after a brief delay
    setTimeout(() => {
      const listMsg = JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/list", params: {} });
      proc.stdin.write(`Content-Length: ${Buffer.byteLength(listMsg)}\r\n\r\n${listMsg}`);
    }, 500);

    // Collect response
    setTimeout(() => {
      proc.kill();

      // Parse JSON-RPC responses from stdout
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

      // Fallback: try to find tools array in any JSON-RPC response
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

// ── Claude Code import ────────────────────────────────────────

async function importFromClaudeCode(): Promise<ChaeshinTool[]> {
  const imported: ChaeshinTool[] = [];

  // Read ~/.claude.json
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

  // For each MCP server, try to get tools
  for (const [serverName, serverConfig] of Object.entries(mcpServers)) {
    if (serverName === "chaeshin") continue; // Skip self

    try {
      const mcpTools = await getMcpTools(
        serverConfig.command,
        serverConfig.args || []
      );

      for (const tool of mcpTools) {
        // Extract params from inputSchema
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

// ── OpenClaw import ───────────────────────────────────────────

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

        // Parse frontmatter
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

// ── Handler ───────────────────────────────────────────────────

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

  // Merge with existing tools (skip duplicates by id)
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
