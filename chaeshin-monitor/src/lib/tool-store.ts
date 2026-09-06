/**
 * Server-side tools.json 읽기/쓰기.
 * ~/.chaeshin/tools.json 또는 CHAESHIN_TOOLS_PATH 환경변수 경로 사용.
 */
import fs from "fs/promises";
import path from "path";
import os from "os";
import type { ChaeshinTool } from "./chaeshin-types";

/** 환경변수 우선으로 도구 레지스트리 JSON 경로를 결정한다. */
export function getToolsPath(): string {
  return process.env.CHAESHIN_TOOLS_PATH || path.join(os.homedir(), ".chaeshin", "tools.json");
}

/** 파일이 없거나 읽을 수 없으면 초기 상태인 빈 레지스트리로 처리한다. */
export async function readTools(): Promise<ChaeshinTool[]> {
  const p = getToolsPath();
  try {
    const data = await fs.readFile(p, "utf-8");
    return JSON.parse(data);
  } catch {
    return [];
  }
}

/** 부모 디렉터리를 보장하고 사람이 검토할 수 있는 들여쓰기 JSON으로 저장한다. */
export async function writeTools(tools: ChaeshinTool[]): Promise<void> {
  const p = getToolsPath();
  await fs.mkdir(path.dirname(p), { recursive: true });
  await fs.writeFile(p, JSON.stringify(tools, null, 2), "utf-8");
}
