"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { createPortal } from "react-dom";
import {
  ComposedChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  usePlotArea,
} from "recharts";
import { Ship, RefreshCw, Calendar } from "lucide-react";
import { cn } from "@/lib/utils";

// ─── Types ────────────────────────────────────────────────────────────────────

interface DataPoint {
  date: string;
  ship_cnt: number;
  duration: number | null;
  anomaly_flag: number | null;
  direction: string | null;
  ratio_low: number | null;
  ratio_high: number | null;
  duration_anomaly_flag: number | null;
  duration_direction: string | null;
  duration_ratio_low: number | null;
  duration_ratio_high: number | null;
  duration_status: string | null;
  regime: string | null;
}

interface ShipCntResponse {
  data: DataPoint[];
  pipes: string[];
  min_date: string | null;
  max_date: string | null;
  selected_name?: string | null;
}

type ChartMetric = "count" | "duration";

// ─── Constants ────────────────────────────────────────────────────────────────

const TIME_WINDOWS = [
  { label: "1M", days: 30 },
  { label: "3M", days: 90 },
  { label: "6M", days: 180 },
  { label: "1Y", days: 365 },
  { label: "All", days: 0 },
];

// anomaly_flag: 0=green, 1=red, 2/3/4=yellow
const ANOMALY_COLORS: Record<number, string> = {
  0: "#10b981",
  1: "#ef4444",
  2: "#f59e0b",
  3: "#f59e0b",
  4: "#f59e0b",
};

const ANOMALY_LABELS: Record<number, string> = {
  0: "绿灯",
  1: "红灯",
  2: "黄灯",
  3: "黄灯",
  4: "黄灯",
};

function formatRatio(value: number | null): string {
  return value == null ? "—" : `${(value * 100).toFixed(0)}%`;
}

function anomalyColor(flag: number | null): string | null {
  if (flag == null) return null;
  return ANOMALY_COLORS[flag] ?? null;
}

interface AnomalyDotProps {
  cx?: number;
  cy?: number;
  payload?: DataPoint;
  metric: ChartMetric;
}

function AnomalyDot({ cx, cy, payload, metric }: AnomalyDotProps) {
  const plot = usePlotArea();
  const value = metric === "count" ? payload?.ship_cnt : payload?.duration;
  if (!plot || !payload || value == null || !Number.isFinite(value) ||
      cx == null || cy == null || !Number.isFinite(cx) || !Number.isFinite(cy)) return <g />;
  const flag = metric === "count" ? payload.anomaly_flag : payload.duration_anomaly_flag;
  const color = anomalyColor(flag);
  if (!color) return <g />;
  const isObvious = flag != null && flag > 0;
  const bottom = plot.y + plot.height;
  return (
    <g>
      {isObvious && cy + 5 < bottom && (
        <line x1={cx} y1={cy + 5} x2={cx} y2={bottom}
          stroke={color} strokeWidth={1} strokeDasharray="3 2" opacity={0.5} />
      )}
      {isObvious && (
        <circle cx={cx} cy={cy} r={6} fill={`${color}20`} stroke={`${color}60`} strokeWidth={1} />
      )}
      <circle cx={cx} cy={cy} r={isObvious ? 3 : 2} fill={color}
        stroke="#0f172a" strokeWidth={isObvious ? 1.5 : 1} />
    </g>
  );
}

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
  metric,
  countLabel,
}: {
  active?: boolean;
  payload?: { value: number | string; payload: DataPoint }[];
  label?: string;
  metric: ChartMetric;
  countLabel: string;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const point = payload[0].payload;
  const anomalyFlag = metric === "count" ? point.anomaly_flag : point.duration_anomaly_flag;
  const flagColor = anomalyColor(anomalyFlag);
  const flagLabel =
    anomalyFlag != null ? ANOMALY_LABELS[anomalyFlag] : null;

  return (
    <div className="bg-navy-800 border border-navy-600 rounded-xl px-3.5 py-2.5 shadow-xl text-xs space-y-1">
      <p className="text-slate-400 font-mono">{label}</p>
      {metric === "count" ? (
        <p className="text-white font-semibold">
          {countLabel}:{" "}
          <span className="text-teal-400 text-sm">{point.ship_cnt}</span>
        </p>
      ) : (
        <p className="text-white font-semibold">
          平均时长:{" "}
          <span className="text-sky-400 text-sm">{point.duration ?? "—"}</span>
        </p>
      )}
      {flagColor && flagLabel && (
        <p className="flex items-center gap-1.5">
          <span
            className="inline-block w-2 h-2 rounded-full"
            style={{ backgroundColor: flagColor }}
          />
          <span style={{ color: flagColor }}>{flagLabel}</span>
        </p>
      )}
      {metric === "duration" && point.duration_status && (
        <p className="text-slate-300">
          数据状态: <span className="text-slate-500">{point.duration_status}</span>
        </p>
      )}
      {metric === "count" && (point.ratio_low != null || point.ratio_high != null) && (
        <p className="text-slate-500">
          数量 L/H: {formatRatio(point.ratio_low)} / {formatRatio(point.ratio_high)}
        </p>
      )}
      {metric === "duration" &&
        (point.duration_ratio_low != null || point.duration_ratio_high != null) && (
        <p className="text-slate-500">
          时长 L/H: {formatRatio(point.duration_ratio_low)} / {formatRatio(point.duration_ratio_high)}
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
  dimension?: "pipe" | "port";
  preferredName?: string;
  title?: string;
  subtitle?: string;
  showDuration?: boolean;
  dashboard?: boolean;
  controlsContainer?: HTMLElement | null;
  onDateSelect?: (date: string) => void;
}

export default function ShipCntChart({
  onFilterChange,
  dimension = "pipe",
  preferredName = "曼德海峡",
  title = "通航船数量",
  subtitle = "Ship count in channel",
  showDuration = false,
  dashboard = false,
  controlsContainer,
  onDateSelect,
}: ShipCntChartProps = {}) {
  const countLabel = dimension === "port" ? "停靠船数量" : "通航船数量";
  const [pipes, setPipes] = useState<string[]>([]);
  const [selectedPipe, setSelectedPipe] = useState<string>("");

  // Overall data bounds from the DB for the selected pipe
  const [minDate, setMinDate] = useState<string>("");
  const [maxDate, setMaxDate] = useState<string>("");

  // Active date range (what's currently displayed)
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");

  // Which quick-select is active (null = custom range)
  const [activeWindow, setActiveWindow] = useState<number | null>(90); // default = 3M
  const [selectedMetric, setMetric] = useState<ChartMetric>("count");
  const metric = showDuration ? selectedMetric : "count";
  const [visiblePlots, setVisiblePlots] = useState<Record<ChartMetric, boolean>>({ count: true, duration: false });
  const displayedMetrics = dashboard
    ? (["count", "duration"] as ChartMetric[]).filter((key) => visiblePlots[key])
    : [metric];

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
          dimension,
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
    [dimension, pipes.length],
  );

  // ── Initial load ───────────────────────────────────────────────────────────

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      try {
        const res = await fetch(
          `/api/ship-cnt?dimension=${encodeURIComponent(dimension)}&preferred_name=${encodeURIComponent(preferredName)}`,
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json: ShipCntResponse = await res.json();
        if (!json.selected_name) {
          setPipes([]);
          setSelectedPipe("");
          setData([]);
          return;
        }
        setPipes(json.pipes);
        setSelectedPipe(json.selected_name);
        const mn = json.min_date ?? "2022-01-01";
        const mx = json.max_date ?? new Date().toISOString().slice(0, 10);
        const defaultStart = (() => {
          const s = subtractDays(mx, 90);
          return s < mn ? mn : s;
        })();
        setMinDate(mn);
        setMaxDate(mx);
        setStartDate(defaultStart);
        setEndDate(mx);
        setData(
          json.data.filter((d) => d.date >= defaultStart && d.date <= mx),
        );
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load chart data");
      } finally {
        setLoading(false);
      }
    };
    init();
  }, [dimension, preferredName]);

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
          `/api/ship-cnt?dimension=${encodeURIComponent(dimension)}&pipe_name=${encodeURIComponent(selectedPipe)}`,
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
        setData(
          json.data.filter((d) => d.date >= newStart && d.date <= newEnd),
        );
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load chart data");
      } finally {
        setLoading(false);
      }
    };
    refetchForPipe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dimension, selectedPipe]);

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

  const latest = data[data.length - 1];
  const previous = data[data.length - 2];
  const isPreviousDay = latest && previous &&
    new Date(latest.date).getTime() - new Date(previous.date).getTime() === 86400000;
  const dailyChange = isPreviousDay && latest.ship_cnt != null && previous.ship_cnt != null
    ? latest.ship_cnt - previous.ship_cnt : null;
  const dailyPercent = dailyChange != null && previous.ship_cnt > 0
    ? (dailyChange / previous.ship_cnt) * 100 : null;
  const durationData = data.map((point) => ({
    ...point,
    duration: point.duration != null && point.duration > 0 ? point.duration : null,
  }));
  const durationSamples = durationData.filter((point) => point.duration != null).length;
  const latestFlag = latest?.anomaly_flag;
  const statusLabel = latestFlag != null
    ? ANOMALY_LABELS[latestFlag] ?? "未评估" : "未评估";
  const directionLabel: Record<string, string> = {
    NORMAL: "正常", LOW: "偏低", HIGH: "偏高", MIXED: "双向波动", UNKNOWN: "未知",
  };

  const controls = (
    <div className={cn("space-y-3", controlsContainer && "rounded-xl border border-navy-700 bg-navy-800/80 px-5 py-4")}>
      {/* ── Row 1: Title + Pipe selector + Refresh ── */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-teal-500/10 border border-teal-500/20 flex items-center justify-center">
            <Ship className="w-4 h-4 text-teal-400" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-white">
              {dashboard ? "通航概览" : metric === "count" ? title : "平均时长"}
            </h2>
            <p className="text-xs text-slate-500">
              {dashboard ? "Traffic overview · 数量与通行时长" : metric === "count" ? subtitle : "Average duration"}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Metric selector */}
          {showDuration && !dashboard && (
          <div
            className="flex items-center gap-1 bg-navy-900 rounded-lg p-0.5 border border-navy-700"
            role="group"
            aria-label="选择图表"
          >
            {([
              { value: "count", label: "船舶数量" },
              { value: "duration", label: "平均时长" },
            ] as { value: ChartMetric; label: string }[]).map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => setMetric(option.value)}
                aria-pressed={metric === option.value}
                className={cn(
                  "px-2.5 py-1 rounded-md text-xs font-medium transition-all",
                  metric === option.value
                    ? "bg-teal-500/20 text-teal-400 border border-teal-500/30"
                    : "text-slate-500 hover:text-slate-300 border border-transparent",
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
          )}

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

      {dashboard && (
        <fieldset className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-slate-300">
          <legend className="sr-only">显示图表</legend>
          <span className="text-xs text-slate-500" aria-hidden="true">显示图表</span>
          {([
            { key: "count", label: "通航船数量" },
            { key: "duration", label: "平均通行时长" },
          ] as { key: ChartMetric; label: string }[]).map(({ key, label }) => (
            <label key={key} className="inline-flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={visiblePlots[key]}
                onChange={(event) => setVisiblePlots((current) => ({ ...current, [key]: event.target.checked }))}
                className="h-4 w-4 accent-teal-500"
              />
              {label}
            </label>
          ))}
        </fieldset>
      )}
    </div>
  );

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className={cn("rounded-xl border border-navy-700 bg-navy-800/80 px-5 py-4 space-y-3", dashboard && "space-y-5")}>
      {controlsContainer ? createPortal(controls, controlsContainer) : controls}

      {dashboard && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3" aria-label="Traffic summary">
          <div className="rounded-xl border border-navy-700 bg-navy-900/60 p-4">
            <p className="text-xs text-slate-500">最新通航量</p>
            <p className="mt-2 text-2xl font-semibold text-white">{loading ? "—" : latest?.ship_cnt ?? "—"}<span className="ml-1 text-xs font-normal text-slate-500">艘</span></p>
            <p className="mt-1 text-xs text-slate-500">{latest?.date ?? "暂无数据"}</p>
          </div>
          <div className="rounded-xl border border-navy-700 bg-navy-900/60 p-4">
            <p className="text-xs text-slate-500">较前一日</p>
            <p className="mt-2 text-2xl font-semibold text-white">{loading || dailyChange == null ? "—" : `${dailyChange > 0 ? "+" : ""}${dailyChange}`}<span className="ml-1 text-xs font-normal text-slate-500">艘</span></p>
            <p className="mt-1 text-xs text-slate-500">{dailyPercent != null ? `${dailyPercent > 0 ? "+" : ""}${dailyPercent.toFixed(1)}%` : "无可比百分比"}</p>
          </div>
          <div className="rounded-xl border border-navy-700 bg-navy-900/60 p-4">
            <p className="text-xs text-slate-500">通航量异常状态</p>
            <p className="mt-2 text-2xl font-semibold" style={{ color: anomalyColor(latestFlag ?? null) ?? "#94a3b8" }}>{loading ? "—" : statusLabel}</p>
            <p className="mt-1 text-xs text-slate-500">{latest?.direction ? directionLabel[latest.direction] ?? "未知" : "尚无检测结果"}</p>
          </div>
        </div>
      )}

      {displayedMetrics.length > 0 && (
        <section className={dashboard ? "border-t border-navy-700 pt-4 space-y-3" : undefined} aria-label="Traffic chart">
          {dashboard && (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-medium text-slate-200">{dashboard ? "通航数量与平均通行时长" : metric === "count" ? "通航船数量" : "平均通行时长"}</h3>
              <span className="text-xs text-slate-500">{"点击日期查看当日分析日志"}</span>
            </div>
          )}
      {/* ── Chart ── */}
      <div className={cn("relative", dashboard ? "h-[350px]" : "h-52")}>
        {displayedMetrics.length === 1 && displayedMetrics[0] === "duration" && durationSamples === 0 && !loading && !error && (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-500">该时段暂无有效通行时长数据</div>
        )}
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
            <ComposedChart
              data={durationData}
              syncId={dashboard ? "workflow-traffic" : undefined}
              onClick={(state) => {
                if (dashboard && typeof state.activeLabel === "string") onDateSelect?.(state.activeLabel);
              }}
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
                <linearGradient
                  id="durationGradient"
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="1"
                >
                  <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#38bdf8" stopOpacity={0} />
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

              {(dashboard ? ["count", "duration"] as ChartMetric[] : [metric]).map((axisMetric) => (
              <YAxis
                key={axisMetric}
                yAxisId={axisMetric}
                dataKey={axisMetric === "count" ? "ship_cnt" : "duration"}
                orientation={dashboard && axisMetric === "duration" ? "right" : "left"}
                allowDecimals={axisMetric !== "count"}
                tick={{ fontSize: 10, fill: "#64748b" }}
                axisLine={false}
                tickLine={false}
                label={{
                  value: axisMetric === "count" ? countLabel : "平均通行时长",
                  angle: -90,
                  position: dashboard && axisMetric === "duration" ? "insideRight" : "insideLeft",
                  offset: 20,
                  fontSize: 10,
                  fill: "#475569",
                }}
              />

              ))}

              <Tooltip content={({ active, payload, label }) => (
                <div className="space-y-1">
                  {displayedMetrics.map((visibleMetric) => {
                    const entry = payload?.find((item) => item.dataKey === (visibleMetric === "count" ? "ship_cnt" : "duration"));
                    if (!entry) return null;
                    return <CustomTooltip key={visibleMetric} active={active} label={String(label ?? "")} metric={visibleMetric} countLabel={countLabel} payload={[{ value: Number(entry.value), payload: entry.payload as DataPoint }]} />;
                  })}
                </div>
              )} />

              {displayedMetrics.map((metric) => (
              <Area
                key={metric}
                yAxisId={metric}
                type="monotone"
                dataKey={metric === "count" ? "ship_cnt" : "duration"}
                stroke={metric === "count" ? "#14b8a6" : "#38bdf8"}
                strokeWidth={1.5}
                fill={metric === "count" ? "url(#shipCntGradient)" : "url(#durationGradient)"}
                connectNulls={false}
                dot={(props) => <AnomalyDot {...props as unknown as AnomalyDotProps} metric={metric} />}
                activeDot={{
                  r: 4,
                  fill: metric === "count" ? "#14b8a6" : "#38bdf8",
                  stroke: "#0f172a",
                  strokeWidth: 2,
                }}
                isAnimationActive={true}
                animationDuration={600}
              />
              ))}
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>

          {dashboard && visiblePlots.duration && (
            <p className="text-xs text-slate-500">{durationSamples} / {data.length} 天有时长数据 · 缺失或零值不连线</p>
          )}
        </section>
      )}

      {/* ── Legend ── */}
      {displayedMetrics.length > 0 && (
      <div className="flex items-center gap-4 text-xs text-slate-500 pt-0.5">
        {displayedMetrics.map((visibleMetric) => (
          <div key={visibleMetric} className="flex items-center gap-1.5">
            <span className={cn("inline-block w-3 h-0.5 rounded", visibleMetric === "count" ? "bg-teal-500" : "bg-sky-400")} />
            <span>{visibleMetric === "count" ? countLabel : "平均时长"}</span>
          </div>
        ))}
        {([
          { color: "#ef4444", label: "红灯" },
          { color: "#f59e0b", label: "黄灯" },
          { color: "#10b981", label: "绿灯" },
        ] as { color: string; label: string }[]).map(({ color, label }) => (
          <div key={label} className="flex items-center gap-1.5">
            <svg width="14" height="14" viewBox="0 0 14 14">
              <circle cx="7" cy="7" r="5" fill={`${color}20`} stroke={`${color}60`} strokeWidth="1" />
              <circle cx="7" cy="7" r="3" fill={color} stroke="#0f172a" strokeWidth="1.5" />
            </svg>
            <span>{label}</span>
          </div>
        ))}
        {selectedPipe && (
          <span className="ml-auto text-slate-600 font-mono">
            {selectedPipe}
          </span>
        )}
      </div>
      )}
    </div>
  );
}
