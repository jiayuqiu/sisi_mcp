from typing import Dict, Any

from pandas import DataFrame

from mcp_conductor.detector.generic.base_detector import BaseDetector
from mcp_conductor.resources.utils.logger import get_logger
from mcp_conductor.resources.utils.sisi_dataclasses import ROLLING_PERCENTILE_FLAG as FLAG

logger = get_logger(__name__)

DIRECTION_NORMAL = "NORMAL"
DIRECTION_LOW = "LOW"
DIRECTION_HIGH = "HIGH"
DIRECTION_MIXED = "MIXED"
DIRECTION_UNKNOWN = "UNKNOWN"

METRIC_SHIP_COUNT = "ship_cnt"
METRIC_DURATION = "duration"
VALID_METRICS = {METRIC_SHIP_COUNT, METRIC_DURATION}


class RollingPercentileDetector(BaseDetector):
    """
    Detects whether a location's recent traffic is anomalous using fitted bounds.

    Strategy:
        1. Receive bounds and threshold fitted offline for the location and run date.
        2. Inspect the stored number of most-recent days.
        3. Count the days outside the stored [lower_bound, upper_bound] band.
        4. Flag when that ratio exceeds the stored anomaly threshold.
    """

    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        super().__init__(config)
        # Retained for callers that use the detector's historical default lookback.
        # The core engine loads all available rows because sparse duration series may
        # need more than one calendar year to supply one scoring interval.
        self.window: int = 365

    def detect(
        self,
        value: DataFrame,
        name_str: str,
        run_date_id: int,
        interval_days: int = 30,
        location_col_name: str = "",
        parameters: dict | None = None,
        metric: str = METRIC_SHIP_COUNT,
    ) -> dict:
        """
        Args:
            value        : historical DataFrame for one location, containing the days
                           to score. Must contain ``date_id`` and the selected metric.
            col_name     : the column name storaging location info.
            name_str     : strait or port name (reserved for future use / logging).
            run_date_id  : reference date in YYYYMMDD (reserved for future use).
            interval_days: number of most-recent days to evaluate. Default 30.
            parameters   : effective m_roll_percentile_parameter row for this
                           location and run date.  Bounds and threshold are fitted
                           offline; they must never be derived from ``value``.
            metric       : ``ship_cnt`` or ``duration``. Duration scoring ignores
                           missing/non-positive duration observations and rows with
                           no contributing ships, matching the fitting rules.

        Returns:
            dict with keys:
                quantile_10   (float) — stored lower metric bound.
                quantile_90   (float) — stored upper metric bound.
                ratio_low     (float) — days below the lower bound / interval_days.
                ratio_high    (float) — days above the upper bound / interval_days.
                direction       (str) — NORMAL, LOW, HIGH, MIXED, or UNKNOWN.
                anomaly_ratio (float) — legacy combined outlier ratio.
                anomaly_flag    (int) — one of:
                    FLAG.NORMAL            (0) — traffic within historical bounds.
                    FLAG.ANOMALY           (1) — outlier ratio exceeds threshold.
                    FLAG.NO_DATA           (2) — all-zero ship_cnt data.
                    FLAG.FLAT_DATA         (3) — p10 == p90, cannot distinguish normal from anomaly.
                    FLAG.INSUFFICIENT_DATA (4) — both p10 and p90 <= 3, counts too small to detect.
        """
        if metric not in VALID_METRICS:
            raise ValueError(f"metric must be one of {sorted(VALID_METRICS)}, got {metric!r}")

        if parameters is None:
            logger.warning("%s on %s has no fitted roll-percentile parameters.", name_str, run_date_id)
            return {"anomaly_flag": FLAG.NO_DATA, "direction": DIRECTION_UNKNOWN}

        if value.empty:
            logger.warning("%s on %s has no source observations to score.", name_str, run_date_id)
            return {"anomaly_flag": FLAG.NO_DATA, "direction": DIRECTION_UNKNOWN}

        status_flags = {
            "NO_DATA": FLAG.NO_DATA,
            "FLAT": FLAG.FLAT_DATA,
            "INSUFFICIENT": FLAG.INSUFFICIENT_DATA,
        }
        status = parameters["status"]
        if status != "OK":
            logger.warning("%s on %s has fitted parameter status %s.", name_str, run_date_id, status)
            return {
                "anomaly_flag": status_flags.get(status, FLAG.NO_DATA),
                "direction": DIRECTION_UNKNOWN,
            }

        lower_bound = parameters["lower_bound"]
        upper_bound = parameters["upper_bound"]
        if lower_bound is None or upper_bound is None:
            logger.error("%s on %s has OK parameters without bounds.", name_str, run_date_id)
            return {"anomaly_flag": FLAG.NO_DATA, "direction": DIRECTION_UNKNOWN}

        interval_days = int(parameters["interval_days"])
        anomaly_threshold = float(parameters["anomaly_threshold"])
        # Keep the legacy output shape while making it explicit that the stored p10/p90
        # bounds are the scoring band (there are no per-run p25/p75 calculations).
        return_dict = {
            "quantile_10": lower_bound,
            "quantile_25": lower_bound,
            "quantile_75": upper_bound,
            "quantile_90": upper_bound,
        }

        scoring_values = value.dropna(subset=[metric])
        if metric == METRIC_DURATION:
            if METRIC_SHIP_COUNT in scoring_values:
                scoring_values = scoring_values[scoring_values[METRIC_SHIP_COUNT].fillna(0) > 0]
            scoring_values = scoring_values[scoring_values[metric] > 0]
        if scoring_values.empty:
            logger.warning("%s on %s has no usable %s observations to score.", name_str, run_date_id, metric)
            return {"anomaly_flag": FLAG.NO_DATA, "direction": DIRECTION_UNKNOWN}

        # Isolate the most recent configured observations. Duration uses the most
        # recent usable observations because its fitted threshold is calibrated on
        # that same non-zero series.
        recent = scoring_values.sort_values(by=["date_id"], ascending=False).head(interval_days)

        latest_value = recent.iloc[0][metric]
        low_count = int((recent[metric] < lower_bound).sum())
        high_count = int((recent[metric] > upper_bound).sum())
        ratio_low = low_count / interval_days
        ratio_high = high_count / interval_days

        if metric == METRIC_SHIP_COUNT and latest_value == 0:
            # When the most recent day has 0 ships, it is always anomalous
            # regardless of percentile bounds.  anomaly_ratio = -1 is a sentinel
            # value meaning "latest day is 0" (distinct from a computed ratio).
            # The directional ratios remain ordinary fractions so new consumers do
            # not need to interpret that legacy sentinel.
            anomaly_flag = FLAG.ANOMALY
            anomaly_ratio = -1.0
            direction = DIRECTION_LOW
        else:
            # flag as anomalous when the outlier ratio exceeds the threshold
            # Divide the combined integer count once to preserve the legacy strict
            # threshold behavior without floating-point addition drift.
            anomaly_ratio = (low_count + high_count) / interval_days
            anomaly_flag = FLAG.ANOMALY if anomaly_ratio > anomaly_threshold else FLAG.NORMAL
            if anomaly_flag == FLAG.NORMAL:
                direction = DIRECTION_NORMAL
            elif ratio_low > ratio_high:
                direction = DIRECTION_LOW
            elif ratio_high > ratio_low:
                direction = DIRECTION_HIGH
            else:
                direction = DIRECTION_MIXED

        return_dict["ratio_low"] = ratio_low
        return_dict["ratio_high"] = ratio_high
        return_dict["direction"] = direction
        return_dict["anomaly_ratio"] = anomaly_ratio
        return_dict["anomaly_flag"] = anomaly_flag
        return return_dict
