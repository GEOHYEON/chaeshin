"use client";

/** 기존 CBR 케이스의 사용자 편집 가능 필드를 수정하는 대화상자. */
import { useState, useEffect } from "react";
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
import { Separator } from "@/components/ui/separator";
import type { ChaeshinCase } from "@/lib/chaeshin-types";
import { Save } from "lucide-react";

interface CaseEditDialogProps {
  caseData: ChaeshinCase | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (updated: ChaeshinCase) => Promise<void>;
}

/** 선택된 케이스를 폼에 복사하고 수정되지 않은 중첩 필드는 저장 시 보존한다. */
export function CaseEditDialog({
  caseData,
  open,
  onOpenChange,
  onSave,
}: CaseEditDialogProps) {
  const [request, setRequest] = useState("");
  const [category, setCategory] = useState("");
  const [keywords, setKeywords] = useState("");
  const [success, setSuccess] = useState(true);
  const [satisfaction, setSatisfaction] = useState(0.85);
  const [errorReason, setErrorReason] = useState("");
  const [tags, setTags] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    // 다른 케이스가 선택될 때 이전 폼 값이 남지 않도록 전체 입력을 다시 채운다.
    if (caseData) {
      setRequest(caseData.problem_features.request);
      setCategory(caseData.problem_features.category);
      setKeywords(caseData.problem_features.keywords.join(", "));
      setSuccess(caseData.outcome.success);
      setSatisfaction(caseData.outcome.user_satisfaction);
      setErrorReason(caseData.outcome.error_reason);
      setTags(caseData.metadata.tags.join(", "));
    }
  }, [caseData]);

  if (!caseData) return null;

  /** 폼 필드만 기존 케이스에 병합하고 수정 시각을 갱신한다. */
  const handleSave = async () => {
    setSaving(true);
    try {
      const updated: ChaeshinCase = {
        ...caseData,
        problem_features: {
          ...caseData.problem_features,
          request,
          category,
          keywords: keywords.split(",").map((k) => k.trim()).filter(Boolean),
        },
        outcome: {
          ...caseData.outcome,
          success,
          user_satisfaction: satisfaction,
          error_reason: errorReason,
        },
        metadata: {
          ...caseData.metadata,
          tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
          updated_at: new Date().toISOString(),
        },
      };
      await onSave(updated);
      onOpenChange(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>케이스 수정</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">요청 (Request)</label>
            <Input value={request} onChange={(e) => setRequest(e.target.value)} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label className="text-sm font-medium">카테고리</label>
              <Input value={category} onChange={(e) => setCategory(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">만족도 (0~1)</label>
              <Input
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={satisfaction}
                onChange={(e) => setSatisfaction(Number(e.target.value))}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium">키워드 (쉼표 구분)</label>
            <Input value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="김치, 찌개, 묵은지" />
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium">태그 (쉼표 구분)</label>
            <Input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="한식, 찌개" />
          </div>

          <Separator />

          <div className="flex items-center gap-2">
            <Checkbox
              id="success"
              checked={success}
              onCheckedChange={(v) => setSuccess(!!v)}
            />
            <label htmlFor="success" className="text-sm">성공 케이스</label>
          </div>

          {!success && (
            <div className="space-y-1.5">
              <label className="text-sm font-medium">실패 사유</label>
              <Input
                value={errorReason}
                onChange={(e) => setErrorReason(e.target.value)}
                placeholder="API rate limit 초과"
              />
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            취소
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            <Save className="h-4 w-4 mr-1.5" />
            {saving ? "저장 중..." : "저장"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
