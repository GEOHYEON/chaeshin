"use client";

import { useEffect, useMemo, useState } from "react";
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
import type { ChaeshinTool } from "@/lib/chaeshin-types";
import { toolApi } from "@/lib/api";
import { Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";

interface SeedGenerateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCompleted: () => void;
}

interface ProgressLine {
  ts: number;
  text: string;
  kind: "log" | "result" | "error";
}

export function SeedGenerateDialog({
  open,
  onOpenChange,
  onCompleted,
}: SeedGenerateDialogProps) {
  const [tools, setTools] = useState<ChaeshinTool[]>([]);
  const [topic, setTopic] = useState("");
  const [selectedToolNames, setSelectedToolNames] = useState<Set<string>>(new Set());
  const [count, setCount] = useState(5);
  const [similarityThreshold, setSimilarityThreshold] = useState(0.85);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<ProgressLine[]>([]);

  useEffect(() => {
    if (!open) return;
    toolApi.getTools().then((res) => {
      setTools(res?.data || []);
    });
    setProgress([]);
  }, [open]);

  const toolsByCategory = useMemo(() => {
    const out = new Map<string, ChaeshinTool[]>();
    for (const t of tools) {
      const cat = t.category || "other";
      if (!out.has(cat)) out.set(cat, []);
      out.get(cat)!.push(t);
    }
    return out;
  }, [tools]);

  const toggleTool = (name: string) => {
    setSelectedToolNames((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const append = (line: ProgressLine) => {
    setProgress((prev) => [...prev, line].slice(-200));
  };

  const handleRun = async () => {
    if (!topic.trim()) {
      toast.error("토픽을 입력해주세요");
      return;
    }
    if (selectedToolNames.size === 0) {
      toast.error("도구를 1개 이상 선택해주세요");
      return;
    }
    setRunning(true);
    setProgress([]);

    try {
      const res = await fetch("/api/seed/generate", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          topic,
          tools: Array.from(selectedToolNames),
          count,
          similarityThreshold,
        }),
      });
      if (!res.body) {
        toast.error("생성 응답을 받을 수 없습니다");
        setRunning(false);
        return;
      }
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      let acceptedCount = 0;
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let nl;
        while ((nl = buf.indexOf("\n")) !== -1) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (!line) continue;
          try {
            const obj = JSON.parse(line) as Record<string, unknown>;
            const ev = String(obj.event || obj.kind || "");
            if (ev === "generate_done") {
              acceptedCount = Number(obj.accepted ?? 0);
              append({
                ts: Date.now(),
                kind: "result",
                text: `생성 완료: 요청 ${obj.requested}건 중 ${obj.accepted}건 수용`,
              });
            } else if (ev === "log") {
              append({ ts: Date.now(), kind: "log", text: String(obj.line || "") });
            } else if (ev === "done") {
              append({
                ts: Date.now(),
                kind: "result",
                text: `프로세스 종료 (exit=${obj.exit_code})`,
              });
            } else if (ev === "error") {
              append({ ts: Date.now(), kind: "error", text: String(obj.message || "") });
            } else {
              append({ ts: Date.now(), kind: "log", text: line });
            }
          } catch {
            append({ ts: Date.now(), kind: "log", text: line });
          }
        }
      }
      toast.success(`${acceptedCount}건 생성됨`);
      onCompleted();
    } catch (e) {
      toast.error(String(e));
    } finally {
      setRunning(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-amber-500" />
            Seed 케이스 생성
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-2">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Topic</label>
            <Input
              placeholder="예: T2DM 진료 / kubectl rollout / monorepo CI 디버깅"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              disabled={running}
            />
          </div>

          <div className="space-y-1.5">
            <div className="flex items-baseline justify-between">
              <label className="text-sm font-medium">도구 allowlist</label>
              <span className="text-xs text-gray-500">
                {selectedToolNames.size} / {tools.length} 선택됨
              </span>
            </div>
            <div className="border rounded p-2 space-y-2">
              {tools.length === 0 && (
                <p className="text-xs text-gray-500 px-1 py-2">
                  ~/.chaeshin/tools.json 에 도구가 없습니다. 먼저 도구를 등록하세요.
                </p>
              )}
              {Array.from(toolsByCategory.entries()).map(([cat, ts]) => (
                <div key={cat}>
                  <div className="text-[11px] uppercase text-gray-400 mb-1">{cat}</div>
                  <div className="flex flex-wrap gap-2">
                    {ts.map((t) => (
                      <label
                        key={t.name}
                        className={`flex items-center gap-1.5 text-xs border rounded px-2 py-1 cursor-pointer ${
                          selectedToolNames.has(t.name)
                            ? "bg-amber-50 border-amber-300"
                            : "bg-white"
                        }`}
                      >
                        <Checkbox
                          checked={selectedToolNames.has(t.name)}
                          onCheckedChange={() => toggleTool(t.name)}
                          disabled={running}
                        />
                        <span>{t.name}</span>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-sm font-medium">생성 수</label>
              <Input
                type="number"
                min={1}
                max={50}
                value={count}
                onChange={(e) => setCount(Number(e.target.value) || 1)}
                disabled={running}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">중복 임계값 (코사인)</label>
              <Input
                type="number"
                step={0.01}
                min={0.5}
                max={0.99}
                value={similarityThreshold}
                onChange={(e) =>
                  setSimilarityThreshold(Number(e.target.value) || 0.85)
                }
                disabled={running}
              />
            </div>
          </div>

          {progress.length > 0 && (
            <>
              <Separator />
              <div className="space-y-1">
                <div className="text-xs font-medium text-gray-600">진행 로그</div>
                <div className="bg-gray-50 border rounded p-2 max-h-48 overflow-y-auto font-mono text-[11px] space-y-0.5">
                  {progress.map((p, i) => (
                    <div
                      key={i}
                      className={
                        p.kind === "error"
                          ? "text-red-600"
                          : p.kind === "result"
                            ? "text-emerald-700 font-medium"
                            : "text-gray-700"
                      }
                    >
                      {p.text}
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>

        <DialogFooter>
          <Badge variant="outline" className="mr-auto text-xs">
            OPENAI_API_KEY 필수
          </Badge>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={running}
          >
            닫기
          </Button>
          <Button onClick={handleRun} disabled={running}>
            {running ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                생성 중…
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4 mr-2" />
                생성 시작
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
