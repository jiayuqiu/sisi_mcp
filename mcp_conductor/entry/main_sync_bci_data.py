import os
import sys
import sqlite3
import logging
import argparse
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

# Ensure we can import from mcp_conductor if run directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mcp_conductor.resources.sisi.APIs.metrics_api import MetricsAPI
from mcp_conductor.entry.main_setup_schema import setup_schema

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = Path("./data/sisi.sqlite")
STATUS_PATH = Path("./data/sync_status.json")
LOG_PATH = Path("./tmp/sync_history.json")
ZBXX_ROUTES = {
    "101-0001": {"table": "ship_cnt_in_port", "key_col": "port_name", "value_col": "ship_cnt", "cast": int},
    "101-0002": {"table": "ship_cnt_in_port", "key_col": "port_name", "value_col": "duration", "cast": float},
    "101-0003": {"table": "ship_cnt_in_pipe", "key_col": "pipe_name", "value_col": "ship_cnt", "cast": int},
    "101-0004": {"table": "ship_cnt_in_pipe", "key_col": "pipe_name", "value_col": "duration", "cast": float},
}

# The upstream API sometimes repeats these canal series under the port metric IDs.
# They are navigation corridors, not ports, and already have authoritative pipe rows.
# Reject only their port-routed items so the valid 101-0003/101-0004 records survive.
PIPE_ONLY_LOCATION_NAMES = frozenset({"巴拿马运河", "苏伊士运河"})


def write_status(status: str, **kwargs):
    """Write sync status to data/sync_status.json and append to tmp/sync_history.json."""
    import json
    payload = {
        "status": status,
        "last_run": datetime.now().isoformat(timespec="seconds"),
        **kwargs,
    }
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


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


def sync_bci_data(start_date: str, end_date: str) -> dict:
    """Fetch metrics from BCI API and save to local SQLite.

    Returns:
        dict: {
            "success": bool,
            "inserted_count": int,
            "reason": str | None,
        }
    """
    write_status("running", start_date=start_date, end_date=end_date)

    api = MetricsAPI()
    # Request batching only — each item's destination comes from its own zbxx.
    zbxxs_groups = [
        "101-0003,101-0004",  # strait: ship count + transit time
        "101-0001,101-0002",  # port: ship count + berthing time
    ]

    fetched_items = []
    api_failures = []
    for zbxxs_val in zbxxs_groups:
        logger.info(
            "Fetching BCI metrics from %s to %s (zbxxs=%s)...",
            start_date,
            end_date,
            zbxxs_val,
        )
        response = api.get_metrics_value(start_date, end_date, zbxxs_val=zbxxs_val)

        if not response or not response.get("success"):
            api_failures.append(
                {
                    "zbxxs": zbxxs_val,
                    "response": response,
                }
            )
            logger.error("API request failed for zbxxs=%s: %s", zbxxs_val, response)
            continue

        result = response.get("result", [])
        if not result:
            logger.warning("No data for zbxxs=%s: %s", zbxxs_val, response)
            continue

        fetched_items.extend(result)

    if api_failures and not fetched_items:
        msg = f"All API requests failed: {api_failures}"
        write_status("failed", start_date=start_date, end_date=end_date, error=msg)
        return {"success": False, "inserted_count": 0, "reason": "api_failed"}

    if not fetched_items:
        msg = "No data in API response for both zbxxs groups"
        logger.warning(msg)
        write_status("failed", start_date=start_date, end_date=end_date, error=msg)
        return {"success": False, "inserted_count": 0, "reason": "empty_result"}

    # Connect to DB
    conn = sqlite3.connect(str(DB_PATH.absolute()))
    cursor = conn.cursor()
    inserted_count = 0
    inserted_by_metric = defaultdict(int)
    malformed_count = 0
    excluded_port_canal_count = 0

    try:
        for item in fetched_items:
            if not isinstance(item, dict):
                continue

            # A malformed item means the API contract broke — log it loudly, but skip
            # only that item. Aborting the whole day would discard the valid rows that
            # arrived alongside it.
            try:
                record_date: str | None = item.get("zbrq")  # YYYY-MM-DD
                if record_date is None:
                    raise ValueError(f"Missing zbrq in item: {item}")

                location_name: str | None = item.get("xftj1Value")
                if location_name is None:
                    raise ValueError(f"Missing xftj1Value in item: {item}")

                value_business_type: str | None = item.get("zbxx")
                if value_business_type is None:
                    raise ValueError(f"Missing zbxx in item: {item}")

                value: str | None = item.get("zbsj")
                if value is None:
                    raise ValueError(f"Missing zbsj in item: {item}")
            except ValueError as e:
                malformed_count += 1
                logger.error("Skipping malformed item: %s", e)
                continue

            zbxx_config_dict = ZBXX_ROUTES.get(value_business_type)
            if zbxx_config_dict is None:
                logger.warning("Skipping item with unroutable zbxx %r: %s", value_business_type, item)
                continue

            if (
                zbxx_config_dict["table"] == "ship_cnt_in_port"
                and location_name in PIPE_ONLY_LOCATION_NAMES
            ):
                excluded_port_canal_count += 1
                logger.warning(
                    "Skipping pipe-only location %s returned under port metric %s.",
                    location_name,
                    value_business_type,
                )
                continue

            # Convert YYYY-MM-DD -> YYYYMMDD
            date_id = int(str(record_date).replace("-", ""))

            try:
                # float() first: the API returns strings, and int("3.0") raises.
                casted_value = zbxx_config_dict['cast'](float(value))
            except (TypeError, ValueError):
                logger.debug("Skipping item with invalid numeric zbsj: %s", item)
                continue

            # Upsert only this metric's column: ship_cnt and duration share a row
            # and arrive as separate zbxx items, so a plain INSERT OR REPLACE
            # would null out whichever one was written first.
            cursor.execute(
                f"""
                INSERT INTO {zbxx_config_dict['table']} ({zbxx_config_dict['key_col']}, date_id, {zbxx_config_dict['value_col']})
                VALUES (?, ?, ?)
                ON CONFLICT({zbxx_config_dict['key_col']}, date_id)
                DO UPDATE SET {zbxx_config_dict['value_col']} = excluded.{zbxx_config_dict['value_col']}
                """,
                (location_name, date_id, casted_value)
            )
            inserted_by_metric[
                f"{zbxx_config_dict['table']}.{zbxx_config_dict['value_col']}"
            ] += cursor.rowcount

        inserted_count = sum(inserted_by_metric.values())

        # Every item was malformed — nothing landed, so the day is a failure even
        # though no single exception escaped the loop.
        if inserted_count == 0 and malformed_count:
            msg = f"All {malformed_count} items were malformed"
            logger.error(msg)
            conn.rollback()
            write_status("failed", start_date=start_date, end_date=end_date, error=msg)
            return {"success": False, "inserted_count": 0, "reason": "malformed_items"}

        conn.commit()
        logger.info(
            "Successfully synced %d records (%s)%s%s.",
            inserted_count,
            ", ".join(f"{k}={v}" for k, v in sorted(inserted_by_metric.items())),
            f", skipped {malformed_count} malformed" if malformed_count else "",
            (
                f", excluded {excluded_port_canal_count} pipe-only port items"
                if excluded_port_canal_count
                else ""
            ),
        )
        write_status("success", start_date=start_date, end_date=end_date, inserted_count=inserted_count)
        return {"success": True, "inserted_count": inserted_count, "reason": None}
    except Exception as e:
        logger.error("Error parsing/inserting data: %s", e)
        conn.rollback()
        write_status("failed", start_date=start_date, end_date=end_date, error=str(e))
        return {"success": False, "inserted_count": 0, "reason": "db_error"}
    finally:
        conn.close()


if __name__ == "__main__":
    setup_schema()

    parser = argparse.ArgumentParser(description="Sync BCI indicator data to local SQLite")
    parser.add_argument("--start-date", type=str, help="Override start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="Override end date (YYYY-MM-DD), defaults to today")
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
