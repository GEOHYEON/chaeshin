"use client";

import { useState, useMemo } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { ChaeshinTool } from "@/lib/chaeshin-types";
import { GripVertical, Plus, Search, Settings, ChevronDown, ChevronRight } from "lucide-react";

interface ToolPaletteProps {
  tools: ChaeshinTool[];
  onAddNode: (tool: ChaeshinTool) => void;
  onManageTools: () => void;
}

export function ToolPalette({ tools, onAddNode, onManageTools }: ToolPaletteProps) {
  const [search, setSearch] = useState("");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const filtered = useMemo(() => {
    if (!search) return tools;
    const q = search.toLowerCase();
    return tools.filter(
      (t) =>
        t.name.toLowerCase().includes(q) ||
        t.display_name.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q)
    );
  }, [tools, search]);

  const grouped = useMemo(() => {
    const map: Record<string, ChaeshinTool[]> = {};
    for (const t of filtered) {
      const cat = t.category || "기타";
      if (!map[cat]) map[cat] = [];
      map[cat].push(t);
    }
    return Object.entries(map).sort(([a], [b]) => a.localeCompare(b));
  }, [filtered]);

  const handleDragStart = (e: React.DragEvent, tool: ChaeshinTool) => {
    e.dataTransfer.setData("application/chaeshin-tool", JSON.stringify(tool));
    e.dataTransfer.effectAllowed = "move";
  };

  const toggleCategory = (cat: string) => {
    setCollapsed((prev) => ({ ...prev, [cat]: !prev[cat] }));
  };

  return (
    <div className="h-full flex flex-col border-l bg-gray-50/50">
      {/* Header */}
      <div className="p-3 border-b space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">도구 팔레트</h3>
          <Button variant="ghost" size="sm" onClick={onManageTools} title="도구 관리">
            <Settings className="h-4 w-4" />
          </Button>
        </div>
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            placeholder="도구 검색..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8 h-8 text-sm"
          />
        </div>
      </div>

      {/* Tool list */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {tools.length === 0 ? (
          <div className="text-center py-8 text-sm text-muted-foreground">
            <p>등록된 도구가 없습니다</p>
            <Button variant="link" size="sm" onClick={onManageTools} className="mt-1">
              도구 추가하기
            </Button>
          </div>
        ) : grouped.length === 0 ? (
          <p className="text-center py-4 text-sm text-muted-foreground">검색 결과 없음</p>
        ) : (
          grouped.map(([category, catTools]) => (
            <div key={category}>
              <button
                onClick={() => toggleCategory(category)}
                className="flex items-center gap-1 w-full px-2 py-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground"
              >
                {collapsed[category] ? (
                  <ChevronRight className="h-3 w-3" />
                ) : (
                  <ChevronDown className="h-3 w-3" />
                )}
                {category}
                <Badge variant="secondary" className="ml-auto text-[10px] px-1.5 py-0">
                  {catTools.length}
                </Badge>
              </button>

              {!collapsed[category] && (
                <div className="space-y-1 ml-1">
                  {catTools.map((tool) => (
                    <div
                      key={tool.id}
                      draggable
                      onDragStart={(e) => handleDragStart(e, tool)}
                      className="flex items-center gap-2 px-2 py-1.5 rounded-md border bg-white hover:bg-blue-50 hover:border-blue-200 cursor-grab active:cursor-grabbing transition-colors group"
                    >
                      <GripVertical className="h-3.5 w-3.5 text-gray-300 group-hover:text-gray-500 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium truncate">{tool.display_name}</div>
                        <div className="text-[11px] text-muted-foreground truncate">{tool.description}</div>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 w-6 p-0 opacity-0 group-hover:opacity-100"
                        onClick={() => onAddNode(tool)}
                        title="캔버스에 추가"
                      >
                        <Plus className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      <div className="p-2 border-t text-[11px] text-muted-foreground text-center">
        드래그하거나 + 클릭으로 추가
      </div>
    </div>
  );
}
