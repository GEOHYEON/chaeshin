"use client";

import Link from "next/link";
import { ChaeshinTab } from "@/components/chaeshin/ChaeshinTab";
import { GitBranch } from "lucide-react";

export default function Home() {
  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="sticky top-0 z-30 border-b bg-white">
        <div className="flex items-center gap-3 px-6 h-14 max-w-7xl mx-auto">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-[hsl(var(--primary))] text-white">
            <GitBranch className="h-4 w-4" />
          </div>
          <div>
            <h1 className="text-base font-semibold tracking-tight">Chaeshin Monitor</h1>
            <p className="text-[11px] text-gray-400 leading-none">CBR 케이스 기반 추론 모니터링</p>
          </div>
          <nav className="ml-auto flex items-center gap-4 text-sm">
            <Link href="/" className="font-medium text-gray-900">Cases</Link>
            <Link href="/events" className="text-gray-500 hover:text-gray-900">Events</Link>
            <Link href="/hierarchy" className="text-gray-500 hover:text-gray-900">Hierarchy</Link>
          </nav>
        </div>
      </header>

      {/* Main */}
      <main className="p-6 max-w-7xl mx-auto">
        <ChaeshinTab />
      </main>
    </div>
  );
}
