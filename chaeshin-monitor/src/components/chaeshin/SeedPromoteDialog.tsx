"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Loader2, Upload } from "lucide-react";
import { toast } from "sonner";

interface SeedPromoteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedIds: string[];
  onPromoted: () => void;
}

export function SeedPromoteDialog({
  open,
  onOpenChange,
  selectedIds,
  onPromoted,
}: SeedPromoteDialogProps) {
  const [force, setForce] = useState(false);
  const [running, setRunning] = useState(false);

  const handlePromote = async () => {
    setRunning(true);
    try {
      const res = await fetch("/api/seed/promote", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ caseIds: selectedIds, force }),
      });
      const data = await res.json();
      if (!res.ok) {
        toast.error(`Promote 실패: ${data.error || res.statusText}`);
        return;
      }
      const payload = data.payload as
        | { promoted?: { old: string; new: string }[]; skipped?: string[] }
        | null;
      const promoted = payload?.promoted?.length ?? 0;
      const skipped = payload?.skipped?.length ?? 0;
      toast.success(`Promote 완료: 새로 ${promoted}건, 스킵 ${skipped}건`);
      onPromoted();
      onOpenChange(false);
    } catch (e) {
      toast.error(String(e));
    } finally {
      setRunning(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Upload className="h-4 w-4 text-emerald-600" />
            Main DB 로 Promote
          </DialogTitle>
          <DialogDescription>
            선택된 {selectedIds.length} 건의 시드 케이스를 main chaeshin.db 로
            복사합니다. 새 case_id 가 발급되며 metadata.source 에{" "}
            <code className="text-xs">promoted_from:&lt;old_id&gt;</code> 마커가 부착됩니다.
          </DialogDescription>
        </DialogHeader>

        <div className="text-xs text-gray-600 space-y-2 bg-gray-50 border rounded p-3">
          <p>
            • 같은 시드를 다시 promote 하면 마커 기반으로 자동 스킵됩니다.
          </p>
          <p>
            • Promote 후 seed/main 은 독립입니다 — seed 수정이 main 으로 전파되지 않습니다.
          </p>
          <p>
            • Outcome 은 항상 <code>pending</code> 으로 들어가며 사용자 verdict 권한은 보호됩니다.
          </p>
        </div>

        <label className="flex items-center gap-2 text-sm">
          <Checkbox
            checked={force}
            onCheckedChange={(v) => setForce(Boolean(v))}
            disabled={running}
          />
          <span>
            <strong>force</strong> — 이미 promote 된 마커가 있어도 새 id 로 한 번 더 발급
          </span>
        </label>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={running}
          >
            취소
          </Button>
          <Button onClick={handlePromote} disabled={running || selectedIds.length === 0}>
            {running ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" /> 진행 중…
              </>
            ) : (
              <>
                <Upload className="h-4 w-4 mr-2" /> Promote {selectedIds.length}건
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
