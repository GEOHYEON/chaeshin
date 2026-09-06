"use client";

/** Mermaid 정의를 브라우저에서 지연 렌더링하고 실패 시 원문으로 대체 표시한다. */
import { useEffect, useRef, useState } from "react";

interface MermaidDiagramProps {
  definition: string;
  className?: string;
}

/** 무거운 Mermaid 모듈을 필요할 때만 로드하는 클라이언트 전용 다이어그램. */
export function MermaidDiagram({ definition, className }: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!definition || !containerRef.current) return;

    // 이전 definition의 비동기 렌더가 늦게 끝나 새 DOM을 덮어쓰지 못하게 한다.
    let cancelled = false;

    async function render() {
      try {
        // 초기 번들 크기를 줄이기 위해 실제 다이어그램이 있을 때 동적 로드한다.
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: "default",
          securityLevel: "loose",
          flowchart: { htmlLabels: true, curve: "basis" },
        });

        if (cancelled) return;

        // Mermaid 내부 SVG 식별자가 같은 페이지의 다른 렌더와 충돌하지 않게 한다.
        const id = `mermaid-${Date.now()}`;
        const { svg } = await mermaid.render(id, definition);

        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg;
          setError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setError(String(e));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    setLoading(true);
    render();

    return () => {
      cancelled = true;
    };
  }, [definition]);

  if (error) {
    // 렌더 오류가 나도 사용자가 정의 자체를 확인하고 수정할 수 있게 남겨 둔다.
    return (
      <div className={className}>
        <pre className="text-xs text-muted-foreground bg-muted p-3 rounded-md overflow-auto whitespace-pre-wrap">
          {definition}
        </pre>
      </div>
    );
  }

  return (
    <div className={className}>
      {loading && (
        <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
          그래프 렌더링 중...
        </div>
      )}
      <div
        ref={containerRef}
        className="overflow-auto [&_svg]:max-w-full [&_svg]:h-auto"
      />
    </div>
  );
}
