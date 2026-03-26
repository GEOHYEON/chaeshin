/**
 * Chaeshin Monitor API client.
 * 독립 프로젝트용 — cases.json API 라우트 호출.
 */

import type { ChaeshinCase, ChaeshinStats } from "./chaeshin-types";

const BASE = "/api/chaeshin";

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
