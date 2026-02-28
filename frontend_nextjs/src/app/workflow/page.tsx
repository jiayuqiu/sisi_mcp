"use client";

import { useState, useEffect, useCallback } from "react";
import { RefreshCw, ChevronLeft, ChevronRight, FileText, Calendar, Tag, Brain } from "lucide-react";
import { cn } from "@/lib/utils";

// ─── Types ────────────────────────────────────────────────────────────────────

interface LogEntry {
  id: number;
  question_type: string | null;
  run_date: string | null;
  content: string | null;
  reasoning_content: string | null;
}

interface LogsResponse {
  logs: LogEntry[];
  total: number;
}

const PAGE_SIZE = 20;

// ─── Helpers ──────────────────────────────────────────────────────────────────

function Badge({ type }: { type: string | null }) {
  const label = type ?? "unknown";
  const colorMap: Record<string, string> = {
    detection: "bg-teal-500/15 text-teal-400 border-teal-500/30",
    analysis:  "bg-accent/15 text-blue-400 border-accent/30",
    unknown:   "bg-slate-500/15 text-slate-400 border-slate-500/30",
  };
  const cls = colorMap[label] ?? colorMap.unknown;
  return (
    <span className={cn("px-2 py-0.5 rounded-full text-xs border font-medium", cls)}>
      {label}
    </span>
  );
}

function Truncated({ text, maxLen = 120 }: { text: string | null; maxLen?: number }) {
  const [expanded, setExpanded] = useState(false);
  if (!text) return <span className="text-slate-600 italic text-xs">—</span>;
  if (text.length <= maxLen) return <span className="text-slate-300 text-xs">{text}</span>;
  return (
    <span className="text-xs">
      <span className="text-slate-300">
        {expanded ? text : text.slice(0, maxLen) + "…"}
      </span>{" "}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="text-teal-400 hover:text-teal-300 underline underline-offset-2 transition-colors"
      >
        {expanded ? "收起" : "展开"}
      </button>
    </span>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function WorkflowPage() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const fetchLogs = useCallback(async (p: number) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/workflow-logs?limit=${PAGE_SIZE}&offset=${p * PAGE_SIZE}`
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: LogsResponse = await res.json();
      setLogs(data.logs);
      setTotal(data.total);
    } catch (e) {
      setError("Failed to fetch logs. Make sure the backend is running.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLogs(page);
  }, [page, fetchLogs]);

  return (
    <div className="flex-1 flex flex-col overflow-hidden px-6 py-5 gap-4 max-w-7xl mx-auto w-full">
      {/* Header */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div>
          <h1 className="text-lg font-semibold text-white">Workflow Inspector</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Agent call history · {total} records total
          </p>
        </div>
        <button
          onClick={() => fetchLogs(page)}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-navy-600 text-slate-400 hover:text-slate-200 hover:border-navy-500 text-sm transition-all disabled:opacity-50"
        >
          <RefreshCw className={cn("w-3.5 h-3.5", loading && "animate-spin")} />
          Refresh
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="flex-shrink-0 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
          ⚠️ {error}
        </div>
      )}

      {/* Table */}
      <div className="flex-1 overflow-auto rounded-xl border border-navy-700 bg-navy-800">
        <table className="w-full text-sm border-collapse">
          <thead className="sticky top-0 bg-navy-700 z-10">
            <tr>
              {[
                { label: "ID",            icon: null,      w: "w-16"  },
                { label: "Type",          icon: Tag,       w: "w-32"  },
                { label: "Run Date",      icon: Calendar,  w: "w-32"  },
                { label: "Content",       icon: FileText,  w: ""      },
                { label: "Reasoning",     icon: Brain,     w: ""      },
              ].map(({ label, icon: Icon, w }) => (
                <th
                  key={label}
                  className={cn(
                    "text-left px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider border-b border-navy-600",
                    w
                  )}
                >
                  <span className="flex items-center gap-1.5">
                    {Icon && <Icon className="w-3.5 h-3.5" />}
                    {label}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={5} className="text-center py-16 text-slate-500 text-sm">
                  <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-teal-500" />
                  Loading logs…
                </td>
              </tr>
            )}
            {!loading && logs.length === 0 && (
              <tr>
                <td colSpan={5} className="text-center py-16 text-slate-500 text-sm">
                  No workflow logs found.
                </td>
              </tr>
            )}
            {!loading &&
              logs.map((log, idx) => (
                <tr
                  key={log.id}
                  className={cn(
                    "border-b border-navy-700/50 transition-colors hover:bg-navy-700/50",
                    idx % 2 === 0 ? "bg-transparent" : "bg-navy-800/50"
                  )}
                >
                  <td className="px-4 py-3 text-slate-500 font-mono text-xs">{log.id}</td>
                  <td className="px-4 py-3">
                    <Badge type={log.question_type} />
                  </td>
                  <td className="px-4 py-3 text-slate-400 text-xs font-mono">
                    {log.run_date ?? "—"}
                  </td>
                  <td className="px-4 py-3 max-w-xs">
                    <Truncated text={log.content} />
                  </td>
                  <td className="px-4 py-3 max-w-xs">
                    <Truncated text={log.reasoning_content} />
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex-shrink-0 flex items-center justify-between text-sm">
        <span className="text-slate-500 text-xs">
          Page {page + 1} of {totalPages} · {total} total records
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0 || loading}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-navy-600 text-slate-400 hover:text-slate-200 hover:border-navy-500 disabled:opacity-40 disabled:cursor-not-allowed transition-all text-xs"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
            Previous
          </button>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1 || loading}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-navy-600 text-slate-400 hover:text-slate-200 hover:border-navy-500 disabled:opacity-40 disabled:cursor-not-allowed transition-all text-xs"
          >
            Next
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
