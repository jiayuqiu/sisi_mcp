"""
Prefect workflow orchestrating the sisi data pipeline.

Dependency graph:
    setup_schema
        |
        v
    sync_bci_data
        |
        v
    traffic_detect
        |
        v
    trigger_dify_chatflow

Usage:
    # Run full pipeline for yesterday
    uv run python workflows/sisi_pipeline.py

    # Run for a specific date range
    uv run python workflows/sisi_pipeline.py --start-date 2024-01-01 --end-date 2024-01-31

    # Run only up to detection (skip Dify chatflow)
    uv run python workflows/sisi_pipeline.py --skip-dify

    # View the flow in Prefect UI (requires prefect server start)
    uv run prefect server start   # in another terminal
    uv run python workflows/sisi_pipeline.py --watch
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add repo root to path so we can import mcp_conductor
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from prefect import flow, task, get_run_logger
from prefect.client.schemas.schedules import CronSchedule

from mcp_conductor.entry.main_setup_schema import setup_schema
from mcp_conductor.entry.main_sync_bci_data import sync_bci_data, get_last_synced_date
from mcp_conductor.entry.main_traffic_detect import traffic_detect
from mcp_conductor.entry.main_trigger_dify_chatflow import (
    run as run_dify_chatflow,
    parse_iso_date,
)


@task(name="setup-schema", retries=1, retry_delay_seconds=5)
def task_setup_schema() -> None:
    """Ensure SQLite database schema exists."""
    logger = get_run_logger()
    logger.info("Setting up database schema...")
    setup_schema()
    logger.info("Schema ready.")


@task(name="sync-bci-data", retries=10, retry_delay_seconds=1800)
def task_sync_bci_data(start_date: str, end_date: str) -> dict:
    """Sync BCI metrics from API to local SQLite."""
    logger = get_run_logger()
    logger.info("Syncing BCI data from %s to %s...", start_date, end_date)

    current = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    total_inserted = 0

    while current <= end_dt:
        day = current.strftime("%Y-%m-%d")
        result = sync_bci_data(day, day)
        if result["success"]:
            total_inserted += result["inserted_count"]
            logger.info("Synced %s: %d records.", day, result["inserted_count"])
        else:
            logger.warning("Sync failed for %s: %s", day, result["reason"])
        current += timedelta(days=1)

    logger.info("Total inserted: %d", total_inserted)
    return {"start_date": start_date, "end_date": end_date, "total_inserted": total_inserted}


@task(name="traffic-detect")
def task_traffic_detect(run_date: str) -> dict:
    """Run rolling percentile anomaly detection."""
    logger = get_run_logger()
    logger.info("Running traffic detection for %s...", run_date)
    traffic_detect(run_date)
    logger.info("Detection complete for %s.", run_date)
    return {"run_date": run_date}


@task(name="trigger-dify-chatflow")
def task_trigger_dify(
    start_date: str,
    end_date: str,
    pipe_filter: str | None = None,
    limit: int | None = None,
    sleep: float = 1.0,
    timeout: float = 600.0,
) -> dict:
    """Trigger Dify chatflow for anomaly rows."""
    logger = get_run_logger()
    logger.info("Triggering Dify chatflow from %s to %s...", start_date, end_date)
    run_dify_chatflow(
        start_date=parse_iso_date(start_date),
        end_date=parse_iso_date(end_date),
        pipe_filter=pipe_filter,
        dry_run=False,
        limit=limit,
        sleep=sleep,
        user="prefect-pipeline",
        timeout=timeout,
    )
    logger.info("Dify chatflow complete.")
    return {"start_date": start_date, "end_date": end_date}


@flow(name="sisi-daily-pipeline", log_prints=True)
def sisi_pipeline(
    start_date: str | None = None,
    end_date: str | None = None,
    skip_dify: bool = False,
    pipe_filter: str | None = None,
    dify_limit: int | None = None,
    dify_sleep: float = 1.0,
) -> dict:
    """
    End-to-end sisi pipeline.

    Args:
        start_date: Sync start date (YYYY-MM-DD). Defaults to day after last sync.
        end_date: Sync end date (YYYY-MM-DD). Defaults to today.
        skip_dify: If True, stop after detection (skip Dify chatflow).
        pipe_filter: Only process this pipe in Dify step.
        dify_limit: Cap Dify calls (useful for testing).
        dify_sleep: Seconds between Dify calls.
    """
    logger = get_run_logger()

    # Resolve dates
    today = datetime.now().strftime("%Y-%m-%d")
    end = end_date or today

    if start_date:
        start = start_date
    else:
        latest = get_last_synced_date()
        if latest:
            start = (datetime.strptime(latest, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
            if start > end:
                logger.info("Already up to date (last synced: %s).", latest)
                return {"status": "up_to_date", "last_synced": latest}
            logger.info("Resuming from %s (last synced: %s).", start, latest)
        else:
            raise ValueError(
                "No records in DB. Pass --start-date or set BCI_SYNC_START_DATE env var."
            )

    logger.info("Pipeline running for %s to %s", start, end)

    # 1. Setup schema
    task_setup_schema()

    # 2. Sync data
    sync_result = task_sync_bci_data(start, end)

    # 3. Detect anomalies (run for each day in range)
    current = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    while current <= end_dt:
        day = current.strftime("%Y-%m-%d")
        task_traffic_detect(day)
        current += timedelta(days=1)

    # 4. Trigger Dify chatflow (optional)
    if not skip_dify:
        task_trigger_dify(
            start_date=start,
            end_date=end,
            pipe_filter=pipe_filter,
            limit=dify_limit,
            sleep=dify_sleep,
        )
    else:
        logger.info("Skipping Dify chatflow (--skip-dify).")

    logger.info("Pipeline complete.")
    return {
        "status": "success",
        "start_date": start,
        "end_date": end,
        "synced_records": sync_result["total_inserted"],
        "skip_dify": skip_dify,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the sisi Prefect pipeline")
    parser.add_argument("--start-date", type=str, help="Override start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="Override end date (YYYY-MM-DD)")
    parser.add_argument("--skip-dify", action="store_true", help="Skip Dify chatflow step")
    parser.add_argument("--pipe", type=str, help="Only process this pipe in Dify step")
    parser.add_argument("--limit", type=int, help="Cap Dify calls")
    parser.add_argument("--sleep", type=float, default=1.0, help="Seconds between Dify calls")
    parser.add_argument("--watch", action="store_true", help="Serve flow for Prefect UI")
    args = parser.parse_args()

    if args.watch:
        # Deploy for local UI viewing with a daily 12:00 schedule
        sisi_pipeline.serve(
            name="sisi-daily-pipeline-local",
            schedule=CronSchedule(cron="0 12 * * *", timezone="Asia/Shanghai"),
        )
    else:
        result = sisi_pipeline(
            start_date=args.start_date,
            end_date=args.end_date,
            skip_dify=args.skip_dify,
            pipe_filter=args.pipe,
            dify_limit=args.limit,
            dify_sleep=args.sleep,
        )
        print(result)


if __name__ == "__main__":
    main()
