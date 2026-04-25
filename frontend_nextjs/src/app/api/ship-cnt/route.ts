import { NextRequest, NextResponse } from "next/server";
import path from "path";
import Database from "better-sqlite3";

const DB_PATH =
  process.env.SQLITE_DB_PATH ??
  path.resolve(process.cwd(), "..", "data", "sisi.sqlite");

interface ShipCntRow {
  date_id: number;
  ship_cnt: number;
  anomaly_flag: number | null;
}

type Dimension = "pipe" | "port";

function resolveDimension(raw: string | null): Dimension {
  return raw === "port" ? "port" : "pipe";
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
  const dimension = resolveDimension(searchParams.get("dimension"));
  const requestedName = searchParams.get("pipe_name");
  const preferredName = searchParams.get("preferred_name") ?? "";
  const start_date = searchParams.get("start_date"); // YYYY-MM-DD
  const end_date = searchParams.get("end_date"); // YYYY-MM-DD
  const days = searchParams.get("days"); // fallback if no start/end

  const sourceTable =
    dimension === "port" ? "ship_cnt_in_port" : "ship_cnt_in_pipe";
  const sourceNameColumn = dimension === "port" ? "port_name" : "pipe_name";

  if (requestedName?.startsWith("test_")) {
    return NextResponse.json(
      { error: "pipe_name is not available" },
      { status: 404 },
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

    const names = (
      db
        .prepare(
          `SELECT DISTINCT ${sourceNameColumn} AS name
           FROM ${sourceTable}
           WHERE ${sourceNameColumn} NOT LIKE 'test\\_%' ESCAPE '\\'
           ORDER BY ${sourceNameColumn}`,
        )
        .all() as { name: string }[]
    ).map((r) => r.name);

    const name = requestedName || (names.includes(preferredName) ? preferredName : names[0]);

    if (!name) {
      db.close();
      return NextResponse.json({
        data: [],
        pipes: [],
        min_date: null,
        max_date: null,
        selected_name: null,
      });
    }

    const rows =
      dimension === "port"
        ? (db
            .prepare(
              `SELECT s.date_id, s.ship_cnt, NULL AS anomaly_flag
               FROM ${sourceTable} s
               WHERE s.${sourceNameColumn} = ? AND s.date_id >= ? AND s.date_id <= ?
               ORDER BY s.date_id ASC`,
            )
            .all(name, startId, endId) as ShipCntRow[])
        : (db
            .prepare(
              `SELECT s.date_id, s.ship_cnt, a.anomaly_flag
               FROM ${sourceTable} s
               LEFT JOIN m_pipe_anomaly_roll_percentile a
                 ON a.pipe_name = s.${sourceNameColumn} AND a.date_id = s.date_id
               WHERE s.${sourceNameColumn} = ? AND s.date_id >= ? AND s.date_id <= ?
               ORDER BY s.date_id ASC`,
            )
            .all(name, startId, endId) as ShipCntRow[]);

    // Fetch overall min/max date_id for this pipe (for date picker bounds)
    const bounds = db
      .prepare(
        `SELECT MIN(date_id) AS min_date_id, MAX(date_id) AS max_date_id
         FROM ${sourceTable} WHERE ${sourceNameColumn} = ?`,
      )
      .get(name) as { min_date_id: number; max_date_id: number };

    db.close();

    // Convert date_id (YYYYMMDD) to ISO date string for the chart
    const data = rows.map((r) => {
      const s = String(r.date_id);
      const dateStr = `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
      return {
        date: dateStr,
        ship_cnt: r.ship_cnt,
        anomaly_flag: r.anomaly_flag ?? null,
      };
    });

    // Convert bounds to ISO strings
    const toIso = (id: number) => {
      const s = String(id);
      return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
    };

    return NextResponse.json({
      data,
      pipes: names,
      min_date: bounds?.min_date_id ? toIso(bounds.min_date_id) : null,
      max_date: bounds?.max_date_id ? toIso(bounds.max_date_id) : null,
      selected_name: name,
    });
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
