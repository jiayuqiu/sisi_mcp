import { NextRequest, NextResponse } from "next/server";
import path from "path";
import Database from "better-sqlite3";

const DB_PATH = process.env.SQLITE_DB_PATH ?? path.resolve(process.cwd(), "..", "data", "sisi.sqlite");

export async function GET(req: NextRequest) {
  const { searchParams } = req.nextUrl;
  const limit = Number(searchParams.get("limit") ?? "50");
  const offset = Number(searchParams.get("offset") ?? "0");

  try {
    const db = new Database(DB_PATH, { readonly: true });

    // Check if table exists
    const tableExists = db
      .prepare(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='log_agent_work_history'"
      )
      .get();

    if (!tableExists) {
      db.close();
      return NextResponse.json({ logs: [], total: 0 });
    }

    const totalRow = db
      .prepare("SELECT COUNT(*) AS cnt FROM log_agent_work_history")
      .get() as { cnt: number };

    const logs = db
      .prepare(
        "SELECT id, question_type, run_date, content, reasoning_content FROM log_agent_work_history ORDER BY run_timestamp DESC LIMIT ? OFFSET ?"
      )
      .all(limit, offset);

    db.close();

    return NextResponse.json({ logs, total: totalRow.cnt });
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : String(e);
    // DB file may not exist yet
    if (message.includes("SQLITE_CANTOPEN") || message.includes("unable to open")) {
      return NextResponse.json({ logs: [], total: 0 });
    }
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
