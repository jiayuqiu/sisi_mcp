import { NextRequest, NextResponse } from "next/server";
import path from "path";
import Database from "better-sqlite3";

const DB_PATH = process.env.SQLITE_DB_PATH ?? path.resolve(process.cwd(), "..", "data", "sisi.sqlite");

function toDateId(iso: string): number {
  return parseInt(iso.replace(/-/g, ""), 10);
}

export async function GET(req: NextRequest) {
  const { searchParams } = req.nextUrl;
  const datesOnly = searchParams.get("dates_only") === "true";
  const limit = Number(searchParams.get("limit") ?? "50");
  const offset = Number(searchParams.get("offset") ?? "0");
  const pipeName = searchParams.get("pipe_name") ?? "";
  const locationType = searchParams.get("location_type") ?? "";
  const startDate = searchParams.get("start_date") ?? "";
  const endDate = searchParams.get("end_date") ?? "";

  try {
    const db = new Database(DB_PATH, { readonly: true });

    const tableExists = db
      .prepare(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='log_agent_worklog'"
      )
      .get();

    if (!tableExists) {
      db.close();
      return NextResponse.json({ logs: [], total: 0, available_dates: [] });
    }

    // Build WHERE clauses
    const conditions: string[] = [];
    const params: (string | number)[] = [];

    if (pipeName) {
      conditions.push("pipe_name = ?");
      params.push(pipeName);
    }
    if (locationType === "pipe" || locationType === "port") {
      conditions.push("location_type = ?");
      params.push(locationType);
    }
    if (startDate) {
      conditions.push("date_id >= ?");
      params.push(toDateId(startDate));
    }
    if (endDate) {
      conditions.push("date_id <= ?");
      params.push(toDateId(endDate));
    }

    const where = conditions.length > 0 ? `WHERE ${conditions.join(" AND ")}` : "";

    if (datesOnly) {
      const rows = db.prepare(`SELECT DISTINCT date_id FROM log_agent_worklog ${where} ORDER BY date_id DESC`)
        .all(...params) as { date_id: number | null }[];
      db.close();
      const dates = rows.flatMap(({ date_id }) => {
        const raw = String(date_id ?? "");
        if (!/^\d{8}$/.test(raw)) return [];
        const iso = `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}`;
        const parsed = new Date(`${iso}T00:00:00Z`);
        return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === iso ? [iso] : [];
      });
      return NextResponse.json({ available_dates: dates });
    }

    const totalRow = db
      .prepare(`SELECT COUNT(*) AS cnt FROM log_agent_worklog ${where}`)
      .get(...params) as { cnt: number };

    const logs = db
      .prepare(
        `SELECT location_type, return_id, question_type, date_id, pipe_name, content, reasoning_content
         FROM log_agent_worklog ${where}
         ORDER BY date_id DESC, run_timestamp DESC LIMIT ? OFFSET ?`
      )
      .all(...params, limit, offset);

    db.close();

    return NextResponse.json({ logs, total: totalRow.cnt });
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : String(e);
    if (message.includes("SQLITE_CANTOPEN") || message.includes("unable to open")) {
      return NextResponse.json({ logs: [], total: 0, available_dates: [] });
    }
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
