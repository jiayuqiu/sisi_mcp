"use client";

import { useState, useEffect, useCallback } from "react";
import ShipCntChart from "@/components/ShipCntChart";
import {
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Brain,
  FileText,
  Calendar,
  Tag,
  Activity,
  Waves,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ─── Types ────────────────────────────────────────────────────────────────────

interface LogEntry {
  return_id: string;
  question_type: string | null;
  date_id: number | null;
  pipe_name: string | null;
  content: string | null;
  reasoning_content: string | null;
}

function formatDateId(dateId: number | null): string {
  if (dateId == null) return "—";
  const s = String(dateId);
  if (s.length !== 8) return s;
  return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
}

interface LogsResponse {
  logs: LogEntry[];
  total: number;
}

const PAGE_SIZE = 10;

// ─── Sub-components ──────────────────────────────────────────────────────────

function Badge({ type }: { type: string | null }) {
  const label = type ?? "unknown";
  const colorMap: Record<string, string> = {
    detection: "bg-teal-500/15 text-teal-400 border-teal-500/30",
    weather_news: "bg-amber-500/15 text-amber-400 border-amber-500/30",
    analysis: "bg-accent/15 text-blue-400 border-accent/30",
    unknown: "bg-slate-500/15 text-slate-400 border-slate-500/30",
  };
  const cls = colorMap[label] ?? colorMap.unknown;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs border font-medium",
        cls,
      )}
    >
      <Tag className="w-3 h-3" />
      {label}
    </span>
  );
}

function LogCard({ log }: { log: LogEntry }) {
  const [expanded, setExpanded] = useState(false);

  const contentPreview = log.content
    ? log.content.length > 150
      ? log.content.slice(0, 150) + "…"
      : log.content
    : null;

  const reasoningPreview = log.reasoning_content
    ? log.reasoning_content.length > 150
      ? log.reasoning_content.slice(0, 150) + "…"
      : log.reasoning_content
    : null;

  const hasLongContent =
    (log.content && log.content.length > 150) ||
    (log.reasoning_content && log.reasoning_content.length > 150);

  return (
    <div
      className={cn(
        "group rounded-xl border border-navy-700 bg-navy-800/80 transition-all duration-200",
        "hover:border-navy-600 hover:bg-navy-800",
      )}
    >
      {/* Card header */}
      <div className="flex items-center justify-between px-5 py-3.5">
        <div className="flex items-center gap-3">
          <span
            className="text-xs font-mono text-slate-600 truncate max-w-[160px]"
            title={log.return_id}
          >
            #{log.return_id}
          </span>
          <Badge type={log.question_type} />
        </div>
        <div className="flex items-center gap-3 text-xs text-slate-500">
          {log.pipe_name && (
            <span className="flex items-center gap-1.5">
              <Waves className="w-3.5 h-3.5" />
              <span>{log.pipe_name}</span>
            </span>
          )}
          <span className="flex items-center gap-1.5">
            <Calendar className="w-3.5 h-3.5" />
            <span className="font-mono">{formatDateId(log.date_id)}</span>
          </span>
        </div>
      </div>

      {/* Card body */}
      <div className="px-5 pb-4 space-y-3">
        {/* Content section */}
        {(log.content || !log.reasoning_content) && (
          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5 text-xs font-medium text-slate-500">
              <FileText className="w-3.5 h-3.5" />
              Content
            </div>
            <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">
              {expanded
                ? log.content
                : (contentPreview ?? (
                    <span className="text-slate-600 italic">No content</span>
                  ))}
            </p>
          </div>
        )}

        {/* Reasoning section */}
        {(log.reasoning_content || expanded) && (
          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5 text-xs font-medium text-slate-500">
              <Brain className="w-3.5 h-3.5" />
              Reasoning
            </div>
            <p className="text-sm text-slate-400 leading-relaxed whitespace-pre-wrap bg-navy-900/50 rounded-lg px-3 py-2.5 border border-navy-700/50">
              {expanded
                ? log.reasoning_content
                : (reasoningPreview ?? (
                    <span className="text-slate-600 italic">No reasoning</span>
                  ))}
            </p>
          </div>
        )}

        {/* Expand / collapse */}
        {hasLongContent && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="flex items-center gap-1 text-xs text-teal-400 hover:text-teal-300 transition-colors pt-1"
          >
            {expanded ? (
              <>
                <ChevronUp className="w-3.5 h-3.5" />
                Collapse
              </>
            ) : (
              <>
                <ChevronDown className="w-3.5 h-3.5" />
                Show full content
              </>
            )}
          </button>
        )}
      </div>
    </div>
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
        `/api/workflow-logs?limit=${PAGE_SIZE}&offset=${p * PAGE_SIZE}`,
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: LogsResponse = await res.json();
      setLogs(data.logs);
      setTotal(data.total);
    } catch {
      setError("Failed to fetch logs. Make sure the backend is running.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLogs(page);
  }, [page, fetchLogs]);

  return (
    <div className="flex-1 flex flex-col overflow-hidden px-6 py-5 gap-5 max-w-4xl mx-auto w-full">
      {/* Ship count chart */}
      <ShipCntChart />

      {/* Header */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-teal-500/10 border border-teal-500/20 flex items-center justify-center">
            <Activity className="w-4.5 h-4.5 text-teal-400" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-white">
              Workflow Inspector
            </h1>
            <p className="text-xs text-slate-500">{total} agent call records</p>
          </div>
        </div>
        <button
          onClick={() => fetchLogs(page)}
          disabled={loading}
          className={cn(
            "flex items-center gap-2 px-3.5 py-2 rounded-xl text-sm transition-all",
            "border border-navy-600 text-slate-400",
            "hover:text-teal-400 hover:border-teal-500/30 hover:bg-teal-500/5",
            "disabled:opacity-50 disabled:cursor-not-allowed",
          )}
        >
          <RefreshCw className={cn("w-3.5 h-3.5", loading && "animate-spin")} />
          Refresh
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="flex-shrink-0 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Cards list */}
      <div className="flex-1 overflow-y-auto space-y-3 pr-1">
        {loading && (
          <div className="flex flex-col items-center justify-center py-20 text-slate-500">
            <RefreshCw className="w-6 h-6 animate-spin text-teal-500 mb-3" />
            <span className="text-sm">Loading records...</span>
          </div>
        )}

        {!loading && logs.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 text-slate-500">
            <FileText className="w-8 h-8 mb-3 text-slate-600" />
            <span className="text-sm">No workflow logs found</span>
          </div>
        )}

        {!loading && logs.map((log) => <LogCard key={log.return_id} log={log} />)}
      </div>

      {/* Pagination */}
      <div className="flex-shrink-0 flex items-center justify-between pt-1">
        <span className="text-xs text-slate-500">
          Page {page + 1} of {totalPages}
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0 || loading}
            className={cn(
              "flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs transition-all",
              "border border-navy-600 text-slate-400",
              "hover:text-slate-200 hover:border-navy-500",
              "disabled:opacity-40 disabled:cursor-not-allowed",
            )}
          >
            <ChevronLeft className="w-3.5 h-3.5" />
            Previous
          </button>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1 || loading}
            className={cn(
              "flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs transition-all",
              "border border-navy-600 text-slate-400",
              "hover:text-slate-200 hover:border-navy-500",
              "disabled:opacity-40 disabled:cursor-not-allowed",
            )}
          >
            Next
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
