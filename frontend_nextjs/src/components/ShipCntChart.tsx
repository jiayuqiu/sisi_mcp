"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Ship, RefreshCw, Calendar } from "lucide-react";
import { cn } from "@/lib/utils";

// ─── Types ────────────────────────────────────────────────────────────────────

interface DataPoint {
  date: string;
  ship_cnt: number;
  detection_flag: string | null;
}

interface ShipCntResponse {
  data: DataPoint[];
  pipes: string[];
  min_date: string | null;
  max_date: string | null;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const TIME_WINDOWS = [
  { label: "1M", days: 30 },
  { label: "3M", days: 90 },
  { label: "6M", days: 180 },
  { label: "1Y", days: 365 },
  { label: "All", days: 0 },
];

const FLAG_COLORS: Record<string, string> = {
  红: "#ef4444",
  黄: "#f59e0b",
  绿: "#10b981",
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function subtractDays(fromDate: string, days: number): string {
  const d = new Date(fromDate);
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

function toDisplayDate(iso: string) {
  return iso; // already YYYY-MM-DD
}

// ─── Custom Tooltip ───────────────────────────────────────────────────────────

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { value: number; payload: DataPoint }[];
  label?: string;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const point = payload[0].payload;
  const flagColor = point.detection_flag
    ? FLAG_COLORS[point.detection_flag]
    : null;

  return (
    <div className="bg-navy-800 border border-navy-600 rounded-xl px-3.5 py-2.5 shadow-xl text-xs space-y-1">
      <p className="text-slate-400 font-mono">{label}</p>
      <p className="text-white font-semibold">
        通航船数量:{" "}
        <span className="text-teal-400 text-sm">{point.ship_cnt}</span>
      </p>
      {point.detection_flag && (
        <p className="flex items-center gap-1.5">
          <span
            className="inline-block w-2 h-2 rounded-full"
            style={{ backgroundColor: flagColor ?? "#94a3b8" }}
          />
          <span style={{ color: flagColor ?? "#94a3b8" }}>
            {point.detection_flag}
          </span>
        </p>
      )}
    </div>
  );
}

// ─── Date Input ───────────────────────────────────────────────────────────────

function DateInput({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: string;
  min?: string;
  max?: string;
  onChange: (v: string) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-xs text-slate-500 whitespace-nowrap">{label}</span>
      <div
        className={cn(
          "flex items-center gap-1 px-2.5 py-1.5 rounded-lg border text-xs",
          "bg-navy-900 border-navy-600 text-slate-300 cursor-pointer",
          "hover:border-teal-500/40 focus-within:border-teal-500/50 transition-colors",
        )}
        onClick={() => ref.current?.showPicker?.()}
      >
        <Calendar className="w-3 h-3 text-slate-500 shrink-0" />
        <input
          ref={ref}
          type="date"
          value={value}
          min={min}
          max={max}
          onChange={(e) => onChange(e.target.value)}
          className="bg-transparent outline-none text-slate-300 w-[88px] cursor-pointer"
        />
      </div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

interface ShipCntChartProps {
  onFilterChange?: (pipe: string, start: string, end: string) => void;
}

export default function ShipCntChart({ onFilterChange }: ShipCntChartProps = {}) {
  const [pipes, setPipes] = useState<string[]>([]);
  const [selectedPipe, setSelectedPipe] = useState<string>("");

  // Overall data bounds from the DB for the selected pipe
  const [minDate, setMinDate] = useState<string>("");
  const [maxDate, setMaxDate] = useState<string>("");

  // Active date range (what's currently displayed)
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");

  // Which quick-select is active (null = custom range)
  const [activeWindow, setActiveWindow] = useState<number | null>(0); // 0 = All

  const [data, setData] = useState<DataPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ── Fetch ──────────────────────────────────────────────────────────────────

  const fetchData = useCallback(
    async (pipe: string, start: string, end: string) => {
      if (!pipe || !start || !end) return;
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams({
          pipe_name: pipe,
          start_date: start,
          end_date: end,
        });
        const res = await fetch(`/api/ship-cnt?${params}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json: ShipCntResponse = await res.json();
        setData(json.data);
        if (pipes.length === 0 && json.pipes.length > 0) setPipes(json.pipes);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load chart data");
      } finally {
        setLoading(false);
      }
    },
    [pipes.length],
  );

  // ── Initial load ───────────────────────────────────────────────────────────

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      try {
        const res = await fetch(
          `/api/ship-cnt?pipe_name=${encodeURIComponent("曼德海峡")}`,
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json: ShipCntResponse = await res.json();
        setPipes(json.pipes);
        setSelectedPipe("曼德海峡");
        const mn = json.min_date ?? "2022-01-01";
        const mx = json.max_date ?? new Date().toISOString().slice(0, 10);
        setMinDate(mn);
        setMaxDate(mx);
        setStartDate(mn);
        setEndDate(mx);
        setData(json.data);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load chart data");
      } finally {
        setLoading(false);
      }
    };
    init();
  }, []);

  // ── Refetch when pipe changes ──────────────────────────────────────────────

  const prevPipe = useRef<string>("");
  useEffect(() => {
    if (!selectedPipe || selectedPipe === prevPipe.current) return;
    prevPipe.current = selectedPipe;

    // Re-fetch bounds for new pipe, then apply current window
    const refetchForPipe = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(
          `/api/ship-cnt?pipe_name=${encodeURIComponent(selectedPipe)}`,
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json: ShipCntResponse = await res.json();
        const mn = json.min_date ?? "2022-01-01";
        const mx = json.max_date ?? new Date().toISOString().slice(0, 10);
        setMinDate(mn);
        setMaxDate(mx);

        // Reapply the active window against new pipe's max_date
        let newStart = mn;
        let newEnd = mx;
        if (activeWindow !== null && activeWindow > 0) {
          newStart = subtractDays(mx, activeWindow);
          if (newStart < mn) newStart = mn;
        }
        setStartDate(newStart);
        setEndDate(newEnd);
        setData(json.data);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load chart data");
      } finally {
        setLoading(false);
      }
    };
    refetchForPipe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPipe]);

  // ── Refetch when date range changes ───────────────────────────────────────

  const isFirstRender = useRef(true);
  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    if (selectedPipe && startDate && endDate) {
      fetchData(selectedPipe, startDate, endDate);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startDate, endDate]);

  // ── Notify parent of filter changes ───────────────────────────────────────

  useEffect(() => {
    if (selectedPipe && startDate && endDate && onFilterChange) {
      onFilterChange(selectedPipe, startDate, endDate);
    }
  }, [selectedPipe, startDate, endDate, onFilterChange]);

  // ── Quick-select handler ───────────────────────────────────────────────────

  const applyWindow = (days: number) => {
    setActiveWindow(days);
    if (!maxDate) return;
    if (days === 0) {
      // "All"
      setStartDate(minDate);
      setEndDate(maxDate);
    } else {
      const newStart = subtractDays(maxDate, days);
      setStartDate(newStart < minDate ? minDate : newStart);
      setEndDate(maxDate);
    }
  };

  // When user manually changes a date input, clear the active quick-select
  const handleStartDateChange = (v: string) => {
    setActiveWindow(null);
    setStartDate(v);
  };
  const handleEndDateChange = (v: string) => {
    setActiveWindow(null);
    setEndDate(v);
  };

  // ── Chart helpers ──────────────────────────────────────────────────────────

  const rangedays =
    startDate && endDate
      ? Math.round(
          (new Date(endDate).getTime() - new Date(startDate).getTime()) /
            86400000,
        )
      : 9999;

  const tickFormatter = (val: string) => {
    if (rangedays <= 90) return val.slice(5); // MM-DD
    return val.slice(0, 7); // YYYY-MM
  };

  const tickInterval = Math.max(0, Math.floor(data.length / 8) - 1);
  const redFlags = data.filter((d) => d.detection_flag === "红");

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="rounded-xl border border-navy-700 bg-navy-800/80 px-5 py-4 space-y-3">
      {/* ── Row 1: Title + Pipe selector + Refresh ── */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-teal-500/10 border border-teal-500/20 flex items-center justify-center">
            <Ship className="w-4 h-4 text-teal-400" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-white">通航船数量</h2>
            <p className="text-xs text-slate-500">Ship count in channel</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Pipe selector */}
          <select
            value={selectedPipe}
            onChange={(e) => setSelectedPipe(e.target.value)}
            className={cn(
              "text-xs rounded-lg px-3 py-1.5 border",
              "bg-navy-900 border-navy-600 text-slate-300",
              "focus:outline-none focus:border-teal-500/50 cursor-pointer",
            )}
          >
            {pipes.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>

          {/* Refresh */}
          <button
            onClick={() => fetchData(selectedPipe, startDate, endDate)}
            disabled={loading}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-all",
              "border border-navy-600 text-slate-400",
              "hover:text-teal-400 hover:border-teal-500/30 hover:bg-teal-500/5",
              "disabled:opacity-50 disabled:cursor-not-allowed",
            )}
          >
            <RefreshCw className={cn("w-3 h-3", loading && "animate-spin")} />
          </button>
        </div>
      </div>

      {/* ── Row 2: Date pickers + Quick-select buttons ── */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* Quick-select */}
        <div className="flex items-center gap-1 bg-navy-900 rounded-lg p-0.5 border border-navy-700">
          {TIME_WINDOWS.map((w) => (
            <button
              key={w.label}
              onClick={() => applyWindow(w.days)}
              className={cn(
                "px-2.5 py-1 rounded-md text-xs font-medium transition-all",
                activeWindow === w.days
                  ? "bg-teal-500/20 text-teal-400 border border-teal-500/30"
                  : "text-slate-500 hover:text-slate-300",
              )}
            >
              {w.label}
            </button>
          ))}
        </div>

        {/* Divider */}
        <span className="text-slate-700 text-xs select-none">|</span>

        {/* Date pickers */}
        <DateInput
          label="从"
          value={startDate}
          min={minDate}
          max={endDate || maxDate}
          onChange={handleStartDateChange}
        />
        <span className="text-slate-600 text-xs">—</span>
        <DateInput
          label="至"
          value={endDate}
          min={startDate || minDate}
          max={maxDate}
          onChange={handleEndDateChange}
        />

        {/* Data count hint */}
        {data.length > 0 && (
          <span className="ml-auto text-xs text-slate-600 font-mono">
            {data.length} 条记录
          </span>
        )}
      </div>

      {/* ── Chart ── */}
      <div className="relative h-52">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-navy-800/60 rounded-lg z-10">
            <RefreshCw className="w-5 h-5 animate-spin text-teal-500" />
          </div>
        )}

        {error && (
          <div className="absolute inset-0 flex items-center justify-center text-red-400 text-xs">
            {error}
          </div>
        )}

        {!error && (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={data}
              margin={{ top: 8, right: 8, left: -16, bottom: 0 }}
            >
              <defs>
                <linearGradient
                  id="shipCntGradient"
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="1"
                >
                  <stop offset="5%" stopColor="#14b8a6" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#14b8a6" stopOpacity={0} />
                </linearGradient>
              </defs>

              <CartesianGrid
                strokeDasharray="3 3"
                stroke="#1e2d3d"
                vertical={false}
              />

              <XAxis
                dataKey="date"
                tickFormatter={tickFormatter}
                interval={tickInterval}
                tick={{ fontSize: 10, fill: "#64748b" }}
                axisLine={{ stroke: "#1e2d3d" }}
                tickLine={false}
                label={{
                  value: "日期",
                  position: "insideBottomRight",
                  offset: -4,
                  fontSize: 10,
                  fill: "#475569",
                }}
              />

              <YAxis
                tick={{ fontSize: 10, fill: "#64748b" }}
                axisLine={false}
                tickLine={false}
                label={{
                  value: "通航船数量",
                  angle: -90,
                  position: "insideLeft",
                  offset: 20,
                  fontSize: 10,
                  fill: "#475569",
                }}
              />

              <Tooltip content={<CustomTooltip />} />

              <Area
                type="monotone"
                dataKey="ship_cnt"
                stroke="#14b8a6"
                strokeWidth={1.5}
                fill="url(#shipCntGradient)"
                dot={(props) => {
                  const { cx, cy, payload } = props as {
                    cx: number;
                    cy: number;
                    payload: DataPoint;
                  };
                  if (payload.detection_flag === "红") {
                    return (
                      <g key={`dot-${payload.date}`}>
                        {/* vertical drop line */}
                        <line
                          x1={cx}
                          y1={0}
                          x2={cx}
                          y2={cy - 5}
                          stroke="#ef4444"
                          strokeWidth={1}
                          strokeDasharray="3 2"
                          opacity={0.5}
                        />
                        {/* outer glow ring */}
                        <circle
                          cx={cx}
                          cy={cy}
                          r={6}
                          fill="#ef444420"
                          stroke="#ef444460"
                          strokeWidth={1}
                        />
                        {/* solid centre dot */}
                        <circle
                          cx={cx}
                          cy={cy}
                          r={3}
                          fill="#ef4444"
                          stroke="#0f172a"
                          strokeWidth={1.5}
                        />
                      </g>
                    );
                  }
                  return <g key={`dot-${payload.date}`} />;
                }}
                activeDot={{
                  r: 4,
                  fill: "#14b8a6",
                  stroke: "#0f172a",
                  strokeWidth: 2,
                }}
                isAnimationActive={true}
                animationDuration={600}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* ── Legend ── */}
      <div className="flex items-center gap-4 text-xs text-slate-500 pt-0.5">
        <div className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-0.5 bg-teal-500 rounded" />
          <span>通航船数量</span>
        </div>
        <div className="flex items-center gap-1.5">
          <svg width="14" height="14" viewBox="0 0 14 14">
            <circle
              cx="7"
              cy="7"
              r="5"
              fill="#ef444420"
              stroke="#ef444460"
              strokeWidth="1"
            />
            <circle
              cx="7"
              cy="7"
              r="3"
              fill="#ef4444"
              stroke="#0f172a"
              strokeWidth="1.5"
            />
          </svg>
          <span>异常标记（红）</span>
        </div>
        {selectedPipe && (
          <span className="ml-auto text-slate-600 font-mono">
            {selectedPipe}
          </span>
        )}
      </div>
    </div>
  );
}
