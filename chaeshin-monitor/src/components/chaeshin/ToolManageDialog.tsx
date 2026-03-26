"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import type { ChaeshinTool, ChaeshinToolParam } from "@/lib/chaeshin-types";
import { toolApi } from "@/lib/api";
import { Plus, Trash2, Pencil, X, Download } from "lucide-react";
import { toast } from "sonner";

async function importTools(source: "claude-code" | "openclaw") {
  const res = await fetch(`/api/tools/import?source=${source}`, { method: "POST" });
  if (!res.ok) throw new Error();
  return res.json() as Promise<{ imported: number; skipped: number; total: number; message?: string }>;
}

interface ToolManageDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  tools: ChaeshinTool[];
  onRefresh: () => void;
}

function emptyParam(): ChaeshinToolParam {
  return { name: "", type: "string", description: "", required: true };
}

export function ToolManageDialog({ open, onOpenChange, tools, onRefresh }: ToolManageDialogProps) {
  const [mode, setMode] = useState<"list" | "form">("list");
  const [editId, setEditId] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);

  // Form state
  const [name, setName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [params, setParams] = useState<ChaeshinToolParam[]>([]);

  const resetForm = () => {
    setName("");
    setDisplayName("");
    setDescription("");
    setCategory("");
    setParams([]);
    setEditId(null);
    setMode("list");
  };

  const openCreateForm = () => {
    resetForm();
    setMode("form");
  };

  const openEditForm = (tool: ChaeshinTool) => {
    setEditId(tool.id);
    setName(tool.name);
    setDisplayName(tool.display_name);
    setDescription(tool.description);
    setCategory(tool.category);
    setParams([...tool.params]);
    setMode("form");
  };

  const handleSave = async () => {
    if (!name.trim()) return;

    const toolData: ChaeshinTool = {
      id: editId || name.replace(/\s+/g, "_").toLowerCase(),
      name,
      display_name: displayName || name,
      description,
      category: category || "기타",
      params: params.filter((p) => p.name.trim()),
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    try {
      if (editId) {
        await toolApi.updateTool(editId, toolData);
        toast.success("도구가 수정되었습니다");
      } else {
        await toolApi.createTool(toolData);
        toast.success("도구가 등록되었습니다");
      }
      onRefresh();
      resetForm();
    } catch {
      toast.error("저장에 실패했습니다");
    }
  };

  const handleDelete = async (toolId: string) => {
    try {
      await toolApi.deleteTool(toolId);
      toast.success("도구가 삭제되었습니다");
      onRefresh();
    } catch {
      toast.error("삭제에 실패했습니다");
    }
  };

  const addParam = () => setParams([...params, emptyParam()]);
  const removeParam = (idx: number) => setParams(params.filter((_, i) => i !== idx));
  const updateParam = (idx: number, field: keyof ChaeshinToolParam, value: unknown) => {
    const updated = [...params];
    (updated[idx] as unknown as Record<string, unknown>)[field] = value;
    setParams(updated);
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) resetForm(); onOpenChange(v); }}>
      <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col p-0 gap-0 overflow-hidden">
        <DialogHeader className="px-6 pt-6 pb-4 border-b shrink-0">
          <DialogTitle>{mode === "list" ? "도구 관리" : editId ? "도구 수정" : "새 도구 등록"}</DialogTitle>
        </DialogHeader>

        <div className="flex-1 min-h-0 overflow-y-auto p-6">
          {mode === "list" ? (
            <div className="space-y-2">
              {tools.length === 0 ? (
                <p className="text-center py-8 text-muted-foreground">등록된 도구가 없습니다</p>
              ) : (
                tools.map((tool) => (
                  <div key={tool.id} className="flex items-center gap-3 p-3 rounded-lg border hover:bg-gray-50">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-sm">{tool.display_name}</span>
                        <Badge variant="outline" className="text-[10px]">{tool.category}</Badge>
                      </div>
                      <div className="text-xs text-muted-foreground mt-0.5">
                        {tool.name} &middot; {tool.params.length}개 파라미터
                      </div>
                    </div>
                    <Button variant="ghost" size="sm" onClick={() => openEditForm(tool)}>
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => handleDelete(tool.id)}>
                      <Trash2 className="h-3.5 w-3.5 text-red-500" />
                    </Button>
                  </div>
                ))
              )}
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <label className="text-sm font-medium">이름 (ID) *</label>
                  <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="taste_check" disabled={!!editId} />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm font-medium">표시명</label>
                  <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="간보기" />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-sm font-medium">설명</label>
                <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="음식의 간을 확인합니다" />
              </div>

              <div className="space-y-1.5">
                <label className="text-sm font-medium">카테고리</label>
                <Input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="검사" />
              </div>

              <Separator />

              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-medium">파라미터</label>
                  <Button variant="outline" size="sm" onClick={addParam}>
                    <Plus className="h-3.5 w-3.5 mr-1" />
                    추가
                  </Button>
                </div>

                {params.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-2">파라미터 없음</p>
                ) : (
                  <div className="space-y-2">
                    {params.map((p, idx) => (
                      <div key={idx} className="flex items-center gap-2 p-2 rounded border bg-gray-50">
                        <Input
                          className="h-8 text-sm flex-1"
                          placeholder="이름"
                          value={p.name}
                          onChange={(e) => updateParam(idx, "name", e.target.value)}
                        />
                        <select
                          className="h-8 text-sm border rounded px-2 bg-white"
                          value={p.type}
                          onChange={(e) => updateParam(idx, "type", e.target.value)}
                        >
                          <option value="string">string</option>
                          <option value="number">number</option>
                          <option value="boolean">boolean</option>
                          <option value="object">object</option>
                          <option value="array">array</option>
                        </select>
                        <Input
                          className="h-8 text-sm flex-[2]"
                          placeholder="설명"
                          value={p.description}
                          onChange={(e) => updateParam(idx, "description", e.target.value)}
                        />
                        <div className="flex items-center gap-1">
                          <Checkbox
                            checked={p.required}
                            onCheckedChange={(v) => updateParam(idx, "required", !!v)}
                          />
                          <span className="text-[11px]">필수</span>
                        </div>
                        <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => removeParam(idx)}>
                          <X className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        <DialogFooter className="px-6 py-4 border-t shrink-0">
          {mode === "list" ? (
            <div className="flex items-center gap-2 w-full">
              {/* Import buttons on the left */}
              <Button
                variant="outline"
                size="sm"
                disabled={importing}
                onClick={async () => {
                  setImporting(true);
                  try {
                    const r = await importTools("claude-code");
                    if (r.imported > 0) {
                      toast.success(`Claude Code에서 ${r.imported}개 도구를 가져왔습니다`);
                      onRefresh();
                    } else {
                      toast.info(r.message || "가져올 도구가 없습니다");
                    }
                  } catch { toast.error("가져오기 실패"); }
                  finally { setImporting(false); }
                }}
              >
                <Download className="h-3.5 w-3.5 mr-1" />
                Claude Code
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={importing}
                onClick={async () => {
                  setImporting(true);
                  try {
                    const r = await importTools("openclaw");
                    if (r.imported > 0) {
                      toast.success(`OpenClaw에서 ${r.imported}개 도구를 가져왔습니다`);
                      onRefresh();
                    } else {
                      toast.info(r.message || "가져올 도구가 없습니다");
                    }
                  } catch { toast.error("가져오기 실패"); }
                  finally { setImporting(false); }
                }}
              >
                <Download className="h-3.5 w-3.5 mr-1" />
                OpenClaw
              </Button>
              <div className="flex-1" />
              <Button variant="outline" onClick={() => onOpenChange(false)}>닫기</Button>
              <Button onClick={openCreateForm}>
                <Plus className="h-4 w-4 mr-1.5" />
                새 도구 등록
              </Button>
            </div>
          ) : (
            <>
              <Button variant="outline" onClick={resetForm}>취소</Button>
              <Button onClick={handleSave} disabled={!name.trim()}>
                {editId ? "수정" : "등록"}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
