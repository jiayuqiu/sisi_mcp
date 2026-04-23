"""
Backfill pipeline: sync BCI data, run traffic detection, trigger Dify chatflow
for each date in a date range.

Usage:
    uv run python -m mcp_conductor.entry.main_backfill \
        --start-date 2026-04-07 --end-date 2026-04-17

    uv run python -m mcp_conductor.entry.main_backfill \
        --start-date 2026-04-07 --end-date 2026-04-17 --dry-run
"""
import argparse
import logging
import sys
import os
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def backfill(
    start_date: str,
    end_date: str,
    dry_run: bool = False,
    sleep: int = 2,
    require_sync_data: bool = False,
):
    """Run the full backfill pipeline for each date in the range."""
    current = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    while current <= end:
        day = current.strftime("%Y-%m-%d")
        logger.info(f"=== Processing {day} ===")

        logger.info(f">>> Syncing BCI data for {day}")
        sync_result = {"success": True, "inserted_count": 0, "reason": None}
        if not dry_run:
            from mcp_conductor.entry.main_sync_bci_data import sync_bci_data
            sync_result = sync_bci_data(day, day)

        if require_sync_data and not sync_result.get("success", False):
            raise RuntimeError(
                f"Sync step failed for {day} (reason={sync_result.get('reason')}). "
                "Stop due to --require-sync-data."
            )

        logger.info(f">>> Running traffic detection for {day}")
        if not dry_run:
            from mcp_conductor.entry.main_traffic_detect import pipe_traffic_detect
            pipe_traffic_detect(day)

        logger.info(f">>> Triggering Dify chatflow for {day}")
        if not dry_run:
            from mcp_conductor.entry.main_trigger_dify_chatflow import run
            from datetime import date as date_class
            run(
                start_date=date_class(current.year, current.month, current.day),
                end_date=date_class(current.year, current.month, current.day),
                pipe_filter=None,
                dry_run=False,
                limit=None,
                sleep=sleep,
                user="backfill-script",
                timeout=180.0,
            )

        current += timedelta(days=1)

    logger.info("=== Backfill complete ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill BCI data, detection, and Dify chatflow")
    parser.add_argument("--start-date", type=str, required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without executing")
    parser.add_argument("--sleep", type=int, default=2, help="Sleep seconds between Dify calls")
    parser.add_argument(
        "--require-sync-data",
        action="store_true",
        help="Fail fast if daily sync returns no data or API failure.",
    )
    args = parser.parse_args()

    backfill(
        args.start_date,
        args.end_date,
        dry_run=args.dry_run,
        sleep=args.sleep,
        require_sync_data=args.require_sync_data,
    )