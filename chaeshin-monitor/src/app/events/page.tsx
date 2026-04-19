"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Activity } from "lucide-react";

interface EventRow {
  id: number;
  ts: string;
  event_type: string;
  session_id: string;
  case_ids: string[];
  payload: Record<string, unknown>;
}

const EVENT_TYPES = [
  "all",
  "retrieve",
  "retain",
  "feedback",
  "decompose_context",
  "stats_viewed",
] as const;

export default function EventsPage() {
  const [events, setEvents] = useState<EventRow[]>([]);
  const [eventType, setEventType] = useState<(typeof EVENT_TYPES)[number]>("all");
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  async function fetchEvents() {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (eventType !== "all") params.set("event_type", eventType);
      params.set("limit", "200");
      const res = await fetch(`/api/events?${params}`);
      const json = await res.json();
      setEvents(json.data || []);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchEvents();
    const t = setInterval(fetchEvents, 5000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventType]);

  const typeCounts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const e of events) m[e.event_type] = (m[e.event_type] || 0) + 1;
    return m;
  }, [events]);

  function toggle(id: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="sticky top-0 z-30 border-b bg-white">
        <div className="flex items-center gap-3 px-6 h-14 max-w-7xl mx-auto">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-[hsl(var(--primary))] text-white">
            <Activity className="h-4 w-4" />
          </div>
          <div>
            <h1 className="text-base font-semibold tracking-tight">Events</h1>
            <p className="text-[11px] text-gray-400 leading-none">MCP 호출 타임라인</p>
          </div>
          <nav className="ml-auto flex items-center gap-4 text-sm">
            <Link href="/" className="text-gray-500 hover:text-gray-900">Cases</Link>
            <Link href="/events" className="font-medium text-gray-900">Events</Link>
            <Link href="/hierarchy" className="text-gray-500 hover:text-gray-900">Hierarchy</Link>
          </nav>
        </div>
      </header>

      <main className="p-6 max-w-7xl mx-auto">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          {EVENT_TYPES.map((t) => (
            <button
              key={t}
              onClick={() => setEventType(t)}
              className={`px-3 py-1 rounded-full text-xs border transition ${
                eventType === t
                  ? "bg-gray-900 text-white border-gray-900"
                  : "bg-white text-gray-600 border-gray-200 hover:border-gray-400"
              }`}
            >
              {t}
              {t !== "all" && typeCounts[t] ? ` (${typeCounts[t]})` : ""}
            </button>
          ))}
          <span className="ml-auto text-xs text-gray-400">
            {loading ? "loading…" : `${events.length} events · auto-refresh 5s`}
          </span>
        </div>

        <div className="rounded-lg border bg-white overflow-hidden">
          {events.length === 0 ? (
            <div className="p-8 text-center text-sm text-gray-400">
              이벤트가 없습니다. MCP 도구(chaeshin_retrieve 등) 호출 후 새로고침하세요.
            </div>
          ) : (
            <ul className="divide-y">
              {events.map((e) => {
                const isOpen = expanded.has(e.id);
                return (
                  <li key={e.id} className="px-4 py-2.5 hover:bg-gray-50">
                    <button
                      onClick={() => toggle(e.id)}
                      className="w-full flex items-center gap-3 text-left"
                    >
                      <span className="text-[10px] font-mono text-gray-400 w-36 shrink-0">
                        {formatTs(e.ts)}
                      </span>
                      <span
                        className={`text-[11px] font-medium px-2 py-0.5 rounded ${typeColor(
                          e.event_type,
                        )}`}
                      >
                        {e.event_type}
                      </span>
                      <span className="text-sm text-gray-700 truncate flex-1">
                        {summarize(e)}
                      </span>
                      {e.case_ids.length > 0 && (
                        <span className="text-[10px] text-gray-400 shrink-0">
                          {e.case_ids.length} case{e.case_ids.length > 1 ? "s" : ""}
                        </span>
                      )}
                      <span className="text-gray-300 text-xs shrink-0">{isOpen ? "▾" : "▸"}</span>
                    </button>
                    {isOpen && (
                      <div className="mt-2 ml-36 text-[11px] font-mono bg-gray-50 border rounded p-2 overflow-auto">
                        <div className="text-gray-500 mb-1">session: {e.session_id || "—"}</div>
                        {e.case_ids.length > 0 && (
                          <div className="text-gray-500 mb-1">
                            case_ids: {e.case_ids.join(", ")}
                          </div>
                        )}
                        <pre className="whitespace-pre-wrap break-all text-gray-800">
                          {JSON.stringify(e.payload, null, 2)}
                        </pre>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </main>
    </div>
  );
}

function formatTs(ts: string): string {
  try {
    const d = new Date(ts);
    return d.toLocaleString("ko-KR", { hour12: false });
  } catch {
    return ts;
  }
}

function typeColor(t: string): string {
  switch (t) {
    case "retrieve":
      return "bg-blue-100 text-blue-700";
    case "retain":
      return "bg-green-100 text-green-700";
    case "feedback":
      return "bg-amber-100 text-amber-700";
    case "decompose_context":
      return "bg-purple-100 text-purple-700";
    case "stats_viewed":
      return "bg-gray-100 text-gray-600";
    default:
      return "bg-gray-100 text-gray-600";
  }
}

function summarize(e: EventRow): string {
  const p = e.payload;
  if (e.event_type === "retrieve") {
    const q = (p.query as string) || "";
    const count = Array.isArray(p.matched_case_ids) ? (p.matched_case_ids as unknown[]).length : 0;
    return `"${q}" → ${count} matches`;
  }
  if (e.event_type === "retain") {
    const req = (p.request as string) || "";
    const layer = (p.layer as string) || "";
    return `[${layer}] ${req}`;
  }
  if (e.event_type === "feedback") {
    const t = (p.feedback_type as string) || "";
    const cid = (p.case_id as string) || "";
    return `${t} · ${cid.slice(0, 8)}`;
  }
  if (e.event_type === "decompose_context") {
    return `"${(p.query as string) || ""}"`;
  }
  return JSON.stringify(p).slice(0, 120);
}
