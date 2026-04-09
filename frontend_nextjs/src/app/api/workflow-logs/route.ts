import { NextRequest, NextResponse } from "next/server";
import path from "path";
import Database from "better-sqlite3";

const DB_PATH = process.env.SQLITE_DB_PATH ?? path.resolve(process.cwd(), "..", "data", "sisi.sqlite");

function toDateId(iso: string): number {
  return parseInt(iso.replace(/-/g, ""), 10);
}

export async function GET(req: NextRequest) {
  const { searchParams } = req.nextUrl;
  const limit = Number(searchParams.get("limit") ?? "50");
  const offset = Number(searchParams.get("offset") ?? "0");
  const pipeName = searchParams.get("pipe_name") ?? "";
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
      return NextResponse.json({ logs: [], total: 0 });
    }

    // Build WHERE clauses
    const conditions: string[] = [];
    const params: (string | number)[] = [];

    if (pipeName) {
      conditions.push("pipe_name = ?");
      params.push(pipeName);
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

    const totalRow = db
      .prepare(`SELECT COUNT(*) AS cnt FROM log_agent_worklog ${where}`)
      .get(...params) as { cnt: number };

    const logs = db
      .prepare(
        `SELECT return_id, question_type, date_id, pipe_name, content, reasoning_content
         FROM log_agent_worklog ${where}
         ORDER BY run_timestamp DESC LIMIT ? OFFSET ?`
      )
      .all(...params, limit, offset);

    db.close();

    return NextResponse.json({ logs, total: totalRow.cnt });
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : String(e);
    if (message.includes("SQLITE_CANTOPEN") || message.includes("unable to open")) {
      return NextResponse.json({ logs: [], total: 0 });
    }
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
