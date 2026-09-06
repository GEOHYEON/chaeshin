/**
 * Chaeshin Monitor 클라이언트 API 모음.
 * 브라우저 컴포넌트에서 SQLite-backed Next.js API 라우트를 일관되게 호출한다.
 */

import type { ChaeshinCase, ChaeshinStats, ChaeshinTool } from "./chaeshin-types";

const BASE = "/api/chaeshin";

/** main CBR 케이스 조회·수정·삭제 클라이언트. */
export const api = {
  async getCases(opts?: {
    category?: string;
    success?: string;
    search?: string;
  }): Promise<{ data: ChaeshinCase[]; total: number }> {
    const params = new URLSearchParams();
    if (opts?.category) params.set("category", opts.category);
    if (opts?.success) params.set("success", opts.success);
    if (opts?.search) params.set("search", opts.search);
    const res = await fetch(`${BASE}?${params}`);
    if (!res.ok) throw new Error("Failed to fetch cases");
    return res.json();
  },

  async getStats(): Promise<ChaeshinStats> {
    const res = await fetch(`${BASE}/stats`);
    if (!res.ok) throw new Error("Failed to fetch stats");
    return res.json();
  },

  async getCase(caseId: string): Promise<ChaeshinCase> {
    const res = await fetch(`${BASE}/${caseId}`);
    if (!res.ok) throw new Error("Failed to fetch case");
    return res.json();
  },

  async updateCase(caseId: string, data: Partial<ChaeshinCase>): Promise<ChaeshinCase> {
    const res = await fetch(`${BASE}/${caseId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error("Failed to update case");
    return res.json();
  },

  async deleteCase(caseId: string): Promise<{ success: boolean }> {
    const res = await fetch(`${BASE}/${caseId}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete case");
    return res.json();
  },
};

// ── 도구 레지스트리 API ────────────────────────────────────

const TOOLS_BASE = "/api/tools";

/** tools.json 기반 도구 레지스트리 클라이언트. */
export const toolApi = {
  async getTools(category?: string): Promise<{ data: ChaeshinTool[]; total: number }> {
    const params = category ? `?category=${encodeURIComponent(category)}` : "";
    const res = await fetch(`${TOOLS_BASE}${params}`);
    if (!res.ok) throw new Error("Failed to fetch tools");
    return res.json();
  },

  async createTool(tool: ChaeshinTool): Promise<{ success: boolean }> {
    const res = await fetch(TOOLS_BASE, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(tool),
    });
    if (!res.ok) throw new Error("Failed to create tool");
    return res.json();
  },

  async updateTool(toolId: string, data: Partial<ChaeshinTool>): Promise<ChaeshinTool> {
    const res = await fetch(`${TOOLS_BASE}/${toolId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error("Failed to update tool");
    return res.json();
  },

  async deleteTool(toolId: string): Promise<{ success: boolean }> {
    const res = await fetch(`${TOOLS_BASE}/${toolId}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete tool");
    return res.json();
  },
};
