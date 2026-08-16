"""
Fit the detection parameters every model reads at serve time and persist them to
m_roll_percentile_parameter.

Run this before detection, and again whenever traffic patterns shift enough that the
stored bounds no longer describe normal. Rows carrying a manual override
(`is_locked = 1`) are left alone.

Usage:
    uv run python mcp_conductor/entry/main_fit_model.py
    uv run python mcp_conductor/entry/main_fit_model.py --dry_run
    uv run python mcp_conductor/entry/main_fit_model.py --location_type pipe --metric duration
    uv run python mcp_conductor/entry/main_fit_model.py --holdout_records 30 --dry_run
"""
import argparse
import logging

from mcp_conductor.detector.roll_percentile.fit import (
    DEFAULT_HOLDOUT_RECORDS,
    DEFAULT_RECENT_RECORDS,
    LOCATION_SPECS,
    STATUS_OK,
    VALID_METRICS,
    fit_roll_percentile_parameters,
)
from mcp_conductor.resources.utils.logger import get_logger

logger = get_logger(__name__)


def fit_model(
    recent_records: int = DEFAULT_RECENT_RECORDS,
    as_of_date_id: int | None = None,
    fit_start: int | None = None,
    location_type: str | None = None,
    metric: str | None = None,
    persist: bool = True,
    holdout_records: int = DEFAULT_HOLDOUT_RECORDS,
) -> list[dict]:
    """
    Fit parameters across every location type and metric.

    Args:
        recent_records: total training-plus-validation budget per location; training
                        is positive-only and ship-count validation retains zeros.
        as_of_date_id : YYYYMMDD; ignore data after this date. Defaults per table to the
                        latest date present.
        fit_start     : optional global YYYYMMDD floor. Built-in location-specific
                        floors still apply, and the later applicable floor wins.
        location_type : restrict to 'pipe' or 'port'; default fits both.
        metric        : restrict to 'ship_cnt' or 'duration'; default fits both.
        persist       : set False to compute without writing.
        holdout_records: latest scoring observations reserved for threshold calibration;
                         ship-count zeros are included.

    Returns:
        Flat list of per-location fit results across every type/metric combination.
    """
    location_types = [location_type] if location_type else sorted(LOCATION_SPECS)
    metrics = [metric] if metric else list(VALID_METRICS)

    results: list[dict] = []
    for _location_type in location_types:
        for _metric in metrics:
            results.extend(
                fit_roll_percentile_parameters(
                    location_type=_location_type,
                    metric=_metric,
                    recent_records=recent_records,
                    as_of_date_id=as_of_date_id,
                    fit_start=fit_start,
                    persist=persist,
                    holdout_records=holdout_records,
                )
            )

    ok = sum(1 for r in results if r.get("status") == STATUS_OK)
    logger.info(
        "Fit complete: %d rows, %d OK, %d unusable, %d skipped as locked.%s",
        len(results),
        ok,
        sum(1 for r in results if r.get("status") not in (STATUS_OK, None)),
        sum(1 for r in results if r.get("skipped") == "locked"),
        " (dry run — nothing written)" if not persist else "",
    )
    return results


def build_parser() -> argparse.ArgumentParser:
    """Build the fitting CLI parser separately so argument behaviour is testable."""
    parser = argparse.ArgumentParser(description="Fit rolling-percentile detection parameters")
    parser.add_argument("--recent_records", type=int, default=DEFAULT_RECENT_RECORDS,
                        help=f"Training-plus-validation budget (default {DEFAULT_RECENT_RECORDS}); 0 = all training history")
    parser.add_argument("--as_of", type=int, default=None,
                        help="Ignore data after this date (YYYYMMDD); default = latest available")
    parser.add_argument("--fit_start", type=int, default=None,
                        help="Optional global floor (YYYYMMDD); later location floors still apply")
    parser.add_argument("--location_type", choices=sorted(LOCATION_SPECS), default=None,
                        help="Restrict to one location type; default fits both")
    parser.add_argument("--metric", choices=list(VALID_METRICS), default=None,
                        help="Restrict to one metric; default fits both")
    parser.add_argument("--dry_run", action="store_true", help="Compute without writing")
    parser.add_argument(
        "--holdout_records",
        type=int,
        default=DEFAULT_HOLDOUT_RECORDS,
        help=f"Latest scoring records reserved for calibration (default {DEFAULT_HOLDOUT_RECORDS}); count zeros included",
    )
    return parser


def main(argv: list[str] | None = None) -> list[dict]:
    """Parse CLI arguments and run fitting; return results for callers and tests."""
    args = build_parser().parse_args(argv)

    return fit_model(
        recent_records=args.recent_records,
        as_of_date_id=args.as_of,
        fit_start=args.fit_start,
        location_type=args.location_type,
        metric=args.metric,
        persist=not args.dry_run,
        holdout_records=args.holdout_records,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    main()
