"""Chronologically refit parameters and rebuild detection results for a date range.

For every detection date, this pipeline fits only through the preceding day. The
resulting parameter version becomes effective on the detection date, preventing
future observations from leaking into historical results.

This entry point intentionally does not synchronize BCI data or trigger Dify. Run it
after the source tables have already been refreshed. It creates daily parameter
versions, so version-aware monitoring snapshots are expected to remain ``WARMING_UP``
during this historical rebuild.

Usage:
    uv run python -m mcp_conductor.entry.main_rebuild_detection \
        --start-date 2026-05-01 --end-date 2026-08-01 --dry-run

    uv run python -m mcp_conductor.entry.main_rebuild_detection \
        --start-date 2026-05-01 --end-date 2026-08-01
"""

import argparse
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mcp_conductor.entry.main_fit_model import fit_model
from mcp_conductor.entry.main_traffic_detect import traffic_detect


logger = logging.getLogger(__name__)

DB_PATH = Path("./data/sisi.sqlite")
BACKUP_DIR = Path("./data/backups")


def backup_database(db_path: Path = DB_PATH, backup_dir: Path = BACKUP_DIR) -> Path:
    """Create a consistent SQLite backup before rebuilding derived tables."""
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path.absolute()}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = backup_dir / f"sisi-before-detection-rebuild-{timestamp}.sqlite"

    with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as destination:
        source.backup(destination)

    logger.info("Created pre-rebuild backup: %s", backup_path)
    return backup_path


def rebuild_detection(
    start_date: str,
    end_date: str,
    *,
    dry_run: bool = False,
    create_backup: bool = True,
) -> list[dict]:
    """Fit through D-1 and detect D for every date in an inclusive range."""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    if start > end:
        raise ValueError("start_date must be on or before end_date")

    if create_backup and not dry_run:
        backup_database()

    completed: list[dict] = []
    current = start
    while current <= end:
        run_date = current.strftime("%Y-%m-%d")
        as_of = current - timedelta(days=1)
        as_of_date_id = int(as_of.strftime("%Y%m%d"))

        logger.info(
            "=== Rebuilding %s (fit through %s) ===",
            run_date,
            as_of.strftime("%Y-%m-%d"),
        )
        fit_results = fit_model(
            as_of_date_id=as_of_date_id,
            persist=not dry_run,
        )

        if dry_run:
            logger.info("Dry run: detection for %s was not executed.", run_date)
        else:
            traffic_detect(run_date)

        completed.append(
            {
                "run_date": run_date,
                "as_of_date_id": as_of_date_id,
                "fit_rows": len(fit_results),
                "detected": not dry_run,
            }
        )
        current += timedelta(days=1)

    logger.info(
        "=== Detection rebuild complete: %d day(s)%s ===",
        len(completed),
        " (dry run)" if dry_run else "",
    )
    return completed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Chronologically refit through D-1 and rebuild detection for D"
    )
    parser.add_argument("--start-date", required=True, help="First detection date (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="Last detection date (YYYY-MM-DD)")
    parser.add_argument(
        "--dry-run",
        "--dry_run",
        action="store_true",
        help="Preview every fit without writing parameters or running detection",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip the automatic pre-rebuild SQLite backup",
    )
    return parser


def main(argv: list[str] | None = None) -> list[dict]:
    args = build_parser().parse_args(argv)
    return rebuild_detection(
        args.start_date,
        args.end_date,
        dry_run=args.dry_run,
        create_backup=not args.no_backup,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    main()
