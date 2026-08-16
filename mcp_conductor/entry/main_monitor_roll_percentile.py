"""Create a live flag-rate monitoring snapshot for corrected detector thresholds.

Usage:
    uv run python mcp_conductor/entry/main_monitor_roll_percentile.py
    uv run python mcp_conductor/entry/main_monitor_roll_percentile.py --dry_run
    uv run python mcp_conductor/entry/main_monitor_roll_percentile.py --end_date 2026-07-26
"""

import argparse
import logging

from mcp_conductor.detector.roll_percentile.monitor import (
    DEFAULT_MIN_ELIGIBLE_SAMPLES,
    DEFAULT_WINDOW_DAYS,
    monitor_roll_percentile,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Monitor rolling-percentile flag rates by location, metric, and direction"
    )
    parser.add_argument(
        "--end_date",
        default=None,
        help="Snapshot end date (YYYY-MM-DD or YYYYMMDD); default = latest detection date",
    )
    parser.add_argument(
        "--window_days",
        type=int,
        default=DEFAULT_WINDOW_DAYS,
        help=f"Requested calendar window (default {DEFAULT_WINDOW_DAYS} days)",
    )
    parser.add_argument(
        "--min_samples",
        type=int,
        default=DEFAULT_MIN_ELIGIBLE_SAMPLES,
        help=f"Eligible results required before alerting (default {DEFAULT_MIN_ELIGIBLE_SAMPLES})",
    )
    parser.add_argument(
        "--alert_rate",
        type=float,
        default=None,
        help="Optional fixed alert rate; default = max(10%%, 2 x fitted target)",
    )
    parser.add_argument("--dry_run", action="store_true", help="Compute without persisting")
    return parser


def main(argv: list[str] | None = None) -> list[dict]:
    args = build_parser().parse_args(argv)
    snapshots = monitor_roll_percentile(
        end_date_id=args.end_date,
        window_days=args.window_days,
        min_eligible_samples=args.min_samples,
        alert_flag_rate=args.alert_rate,
        persist=not args.dry_run,
    )

    print("location_type\tlocation_name\tmetric\teligible\tflagged\tflag_rate\tstatus")
    for row in snapshots:
        if row["direction"] != "ANY":
            continue
        rate = "" if row["flag_rate"] is None else f"{row['flag_rate']:.2%}"
        print(
            f"{row['location_type']}\t{row['location_name']}\t{row['metric']}\t" + \
            f"{row['eligible_count']}\t{row['flagged_count']}\t{rate}\t{row['status']}"
        )
    return snapshots


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    main()
