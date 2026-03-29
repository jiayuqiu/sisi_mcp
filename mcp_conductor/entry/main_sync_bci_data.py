import os
import sys
import sqlite3
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Ensure we can import from mcp_conductor if run directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mcp_conductor.resources.sisi.APIs.metrics_api import MetricsAPI

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = Path("./data/sisi.sqlite")
STATUS_PATH = Path("./data/sync_status.json")


def write_status(status: str, **kwargs):
    """Write sync status to data/sync_status.json."""
    import json
    payload = {
        "status": status,
        "last_run": datetime.now().isoformat(timespec="seconds"),
        **kwargs,
    }
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_last_synced_date() -> str | None:
    """Return the most recent synced date in ship_cnt_in_pipe as YYYY-MM-DD, or None if table is empty."""
    conn = sqlite3.connect(str(DB_PATH.absolute()))
    try:
        row = conn.execute("SELECT MAX(date_id) FROM ship_cnt_in_pipe").fetchone()
        max_id = row[0] if row else None
        if max_id:
            return datetime.strptime(str(max_id), "%Y%m%d").strftime("%Y-%m-%d")
        return None
    finally:
        conn.close()


def sync_bci_data(start_date: str, end_date: str):
    """Fetch metrics from BCI API and save to local SQLite."""
    write_status("running", start_date=start_date, end_date=end_date)

    api = MetricsAPI()
    logger.info("Fetching BCI metrics from %s to %s...", start_date, end_date)

    response = api.get_canal_traffic(start_date, end_date)

    if not response or not response.get("success"):
        msg = f"API request failed: {response}"
        logger.error(msg)
        write_status("failed", start_date=start_date, end_date=end_date, error=msg)
        return

    data = response.get("result", [])
    if not data:
        msg = f"No data in API response: {response}"
        logger.warning(msg)
        write_status("failed", start_date=start_date, end_date=end_date, error=msg)
        return

    # Connect to DB
    conn = sqlite3.connect(str(DB_PATH.absolute()))
    cursor = conn.cursor()
    inserted_count = 0

    try:
        for item in data:
            if not isinstance(item, dict):
                continue

            record_date = item.get("zbrq")       # YYYY-MM-DD
            pipe_name = item.get("xftj1Value")   # e.g. '马六甲海峡'
            value = item.get("zbsj")             # ship count

            if not record_date or not pipe_name or value is None:
                logger.debug("Skipping item with missing fields: %s", item)
                continue

            # Convert YYYY-MM-DD -> YYYYMMDD
            date_id = int(str(record_date).replace("-", ""))

            cursor.execute(
                """
                INSERT OR IGNORE INTO ship_cnt_in_pipe (pipe_name, date_id, ship_cnt, detection_flag)
                VALUES (?, ?, ?, NULL)
                """,
                (pipe_name, date_id, int(value))
            )
            inserted_count += cursor.rowcount

        conn.commit()
        logger.info("Successfully synced %d records into ship_cnt_in_pipe.", inserted_count)
        write_status("success", start_date=start_date, end_date=end_date, inserted_count=inserted_count)
    except Exception as e:
        logger.error("Error parsing/inserting data: %s", e)
        conn.rollback()
        write_status("failed", start_date=start_date, end_date=end_date, error=str(e))
    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync BCI indicator data to local SQLite")
    parser.add_argument("--start_date", type=str, help="Override start date (YYYY-MM-DD)")
    parser.add_argument("--end_date", type=str, help="Override end date (YYYY-MM-DD), defaults to today")
    args = parser.parse_args()

    today = datetime.now().strftime("%Y-%m-%d")
    end = args.end_date or today

    if args.start_date:
        start = args.start_date
    else:
        latest_synced_date = get_last_synced_date()
        if latest_synced_date:
            start = (datetime.strptime(latest_synced_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
            if start > end:
                logger.info("Already up to date (last synced: %s).", latest_synced_date)
                raise SystemExit(0)
            logger.info("Resuming from %s (last synced: %s).", start, latest_synced_date)
        else:
            env_start = os.getenv("BCI_SYNC_START_DATE")
            if env_start:
                logger.info("No records in DB. Using BCI_SYNC_START_DATE=%s for initial sync.", env_start)
                start = env_start
            else:
                logger.error(
                    "No records found in DB. Set BCI_SYNC_START_DATE env var or pass --start_date. "
                    "Example: --start_date 2022-01-01"
                )
                raise SystemExit(1)

    # Sync day by day so each day's result is committed independently.
    # On failure, the next run resumes from the last successfully synced date.
    current = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    while current <= end_dt:
        day = current.strftime("%Y-%m-%d")
        logger.info("Syncing %s ...", day)
        sync_bci_data(day, day)
        current += timedelta(days=1)