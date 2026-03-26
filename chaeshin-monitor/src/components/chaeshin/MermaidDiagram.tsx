"use client";

import { useEffect, useRef, useState } from "react";

interface MermaidDiagramProps {
  definition: string;
  className?: string;
}

export function MermaidDiagram({ definition, className }: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!definition || !containerRef.current) return;

    let cancelled = false;

    async function render() {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: "default",
          securityLevel: "loose",
          flowchart: { htmlLabels: true, curve: "basis" },
        });

        if (cancelled) return;

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
