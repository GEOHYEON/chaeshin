/**
 * Server-side cases.json 읽기/쓰기.
 * ~/.chaeshin/cases.json 또는 CHAESHIN_CASES_PATH 환경변수 경로 사용.
 */
import fs from "fs/promises";
import path from "path";
import os from "os";

export function getCasesPath(): string {
  return process.env.CHAESHIN_CASES_PATH || path.join(os.homedir(), ".chaeshin", "cases.json");
}

export async function readCases(): Promise<unknown[]> {
  const p = getCasesPath();
  try {
    const data = await fs.readFile(p, "utf-8");
    return JSON.parse(data);
  } catch {
    return [];
  }
}

export async function writeCases(cases: unknown[]): Promise<void> {
  const p = getCasesPath();
  await fs.mkdir(path.dirname(p), { recursive: true });
  await fs.writeFile(p, JSON.stringify(cases, null, 2), "utf-8");
}
