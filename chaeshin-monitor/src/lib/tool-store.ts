/**
 * Server-side tools.json 읽기/쓰기.
 * ~/.chaeshin/tools.json 또는 CHAESHIN_TOOLS_PATH 환경변수 경로 사용.
 */
import fs from "fs/promises";
import path from "path";
import os from "os";
import type { ChaeshinTool } from "./chaeshin-types";

export function getToolsPath(): string {
  return process.env.CHAESHIN_TOOLS_PATH || path.join(os.homedir(), ".chaeshin", "tools.json");
}

export async function readTools(): Promise<ChaeshinTool[]> {
  const p = getToolsPath();
  try {
    const data = await fs.readFile(p, "utf-8");
    return JSON.parse(data);
  } catch {
    return [];
  }
}

export async function writeTools(tools: ChaeshinTool[]): Promise<void> {
  const p = getToolsPath();
  await fs.mkdir(path.dirname(p), { recursive: true });
  await fs.writeFile(p, JSON.stringify(tools, null, 2), "utf-8");
}
