"use client";

import { ChaeshinTab } from "@/components/chaeshin/ChaeshinTab";
import { GitBranch } from "lucide-react";

export default function Home() {
  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur">
        <div className="flex items-center gap-3 px-6 h-14">
          <GitBranch className="h-5 w-5 text-primary" />
          <div>
            <h1 className="text-lg font-semibold">Chaeshin Monitor</h1>
            <p className="text-xs text-muted-foreground">CBR 케이스 기반 추론 모니터링</p>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="p-6 max-w-7xl mx-auto">
        <ChaeshinTab />
      </main>
    </div>
  );
}
