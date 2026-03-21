import { NextRequest, NextResponse } from "next/server";
import path from "path";
import Database from "better-sqlite3";

const DB_PATH =
  process.env.SQLITE_DB_PATH ??
  path.resolve(process.cwd(), "..", "data", "sisi.sqlite");

interface ShipCntRow {
  date_id: number;
  ship_cnt: number;
  detection_flag: string | null;
}

function toDateId(dateStr: string): number {
  // dateStr is YYYY-MM-DD
  return parseInt(dateStr.replace(/-/g, ""), 10);
}

function daysAgoDateId(days: number): number {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.getFullYear() * 10000 + (d.getMonth() + 1) * 100 + d.getDate();
}

export async function GET(req: NextRequest) {
  const { searchParams } = req.nextUrl;
  const pipe_name = searchParams.get("pipe_name");
  const start_date = searchParams.get("start_date"); // YYYY-MM-DD
  const end_date = searchParams.get("end_date"); // YYYY-MM-DD
  const days = searchParams.get("days"); // fallback if no start/end

  if (!pipe_name) {
    return NextResponse.json(
      { error: "pipe_name is required" },
      { status: 400 },
    );
  }

  // Resolve cutoff date_ids
  let startId: number;
  let endId: number = 99991231; // far future — no upper bound by default

  if (start_date) {
    startId = toDateId(start_date);
  } else if (days) {
    startId = daysAgoDateId(Number(days));
  } else {
    startId = 0; // all data
  }

  if (end_date) {
    endId = toDateId(end_date);
  }

  try {
    const db = new Database(DB_PATH, { readonly: true });

    const rows = db
      .prepare(
        `SELECT date_id, ship_cnt, detection_flag
         FROM ship_cnt_in_pipe
         WHERE pipe_name = ? AND date_id >= ? AND date_id <= ?
         ORDER BY date_id ASC`,
      )
      .all(pipe_name, startId, endId) as ShipCntRow[];

    // Also fetch all distinct pipe names for the selector
    const pipes = (
      db
        .prepare(
          "SELECT DISTINCT pipe_name FROM ship_cnt_in_pipe ORDER BY pipe_name",
        )
        .all() as { pipe_name: string }[]
    ).map((r) => r.pipe_name);

    // Fetch overall min/max date_id for this pipe (for date picker bounds)
    const bounds = db
      .prepare(
        `SELECT MIN(date_id) AS min_date_id, MAX(date_id) AS max_date_id
         FROM ship_cnt_in_pipe WHERE pipe_name = ?`,
      )
      .get(pipe_name) as { min_date_id: number; max_date_id: number };

    db.close();

    // Convert date_id (YYYYMMDD) to ISO date string for the chart
    const data = rows.map((r) => {
      const s = String(r.date_id);
      const dateStr = `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
      return {
        date: dateStr,
        ship_cnt: r.ship_cnt,
        detection_flag: r.detection_flag ?? null,
      };
    });

    // Convert bounds to ISO strings
    const toIso = (id: number) => {
      const s = String(id);
      return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
    };

    return NextResponse.json({
      data,
      pipes,
      min_date: bounds?.min_date_id ? toIso(bounds.min_date_id) : null,
      max_date: bounds?.max_date_id ? toIso(bounds.max_date_id) : null,
    });
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
