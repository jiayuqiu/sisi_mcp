from typing import Dict, Any

from pandas import DataFrame

from mcp_conductor.detector.generic.base_detector import BaseDetector
from mcp_conductor.resources.utils.logger import get_logger
from mcp_conductor.resources.utils.sisi_dataclasses import ROLLING_PERCENTILE_FLAG as FLAG

logger = get_logger(__name__)


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
        # The engine uses this to load enough recent source rows for the default
        # scoring interval. Bounds are never calculated from this window.
        self.window: int = 365

    def detect(
        self,
        value: DataFrame,
        name_str: str,
        run_date_id: int,
        interval_days: int = 30,
        location_col_name: str = "",
        parameters: dict | None = None,
    ) -> dict:
        """
        Args:
            value        : historical DataFrame for one strait, containing the days to score.
                           must contain columns [date_id, ship_cnt].
            col_name     : the column name storaging location info.
            name_str     : strait or port name (reserved for future use / logging).
            run_date_id  : reference date in YYYYMMDD (reserved for future use).
            interval_days: number of most-recent days to evaluate. Default 30.
            parameters   : effective m_roll_percentile_parameter row for this
                           location and run date.  Bounds and threshold are fitted
                           offline; they must never be derived from ``value``.

        Returns:
            dict with keys:
                quantile_10   (float) — 10th-percentile ship count.
                quantile_90   (float) — 90th-percentile ship count.
                anomaly_ratio (float) — anomaly_cnt / interval_days
                anomaly_flag (int)   — one of:
                    FLAG.NORMAL            (0) — traffic within historical bounds.
                    FLAG.ANOMALY           (1) — outlier ratio exceeds threshold.
                    FLAG.NO_DATA           (2) — all-zero ship_cnt data.
                    FLAG.FLAT_DATA         (3) — p10 == p90, cannot distinguish normal from anomaly.
                    FLAG.INSUFFICIENT_DATA (4) — both p10 and p90 <= 3, counts too small to detect.
        """
        if parameters is None:
            logger.warning("%s on %s has no fitted roll-percentile parameters.", name_str, run_date_id)
            return {"anomaly_flag": FLAG.NO_DATA}

        if value.empty:
            logger.warning("%s on %s has no source observations to score.", name_str, run_date_id)
            return {"anomaly_flag": FLAG.NO_DATA}

        status_flags = {
            "NO_DATA": FLAG.NO_DATA,
            "FLAT": FLAG.FLAT_DATA,
            "INSUFFICIENT": FLAG.INSUFFICIENT_DATA,
        }
        status = parameters["status"]
        if status != "OK":
            logger.warning("%s on %s has fitted parameter status %s.", name_str, run_date_id, status)
            return {"anomaly_flag": status_flags.get(status, FLAG.NO_DATA)}

        lower_bound = parameters["lower_bound"]
        upper_bound = parameters["upper_bound"]
        if lower_bound is None or upper_bound is None:
            logger.error("%s on %s has OK parameters without bounds.", name_str, run_date_id)
            return {"anomaly_flag": FLAG.NO_DATA}

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

        # isolate the most recent `interval_days` rows
        recent = value.sort_values(by=["date_id"], ascending=False).head(interval_days)

        latest_row = recent.iloc[0]
        latest_ship_cnt = latest_row["ship_cnt"]

        if latest_ship_cnt == 0:
            # When the most recent day has 0 ships, it is always anomalous
            # regardless of percentile bounds.  anomaly_ratio = -1 is a sentinel
            # value meaning "latest day is 0" (distinct from a computed ratio).
            anomaly_flag = FLAG.ANOMALY
            anomaly_ratio = -1.0
        else:
            # latest ship cnt != 0
            # count days whose ship_cnt falls outside [p10, p90]
            anomaly_cnt = 0
            for _, row in recent.iterrows():
                if (row["ship_cnt"] < lower_bound) or (row["ship_cnt"] > upper_bound):
                    anomaly_cnt += 1

            # flag as anomalous when the outlier ratio exceeds the threshold
            anomaly_ratio = anomaly_cnt / interval_days
            anomaly_flag = FLAG.ANOMALY if anomaly_ratio > anomaly_threshold else FLAG.NORMAL

        return_dict["anomaly_ratio"] = anomaly_ratio
        return_dict["anomaly_flag"] = anomaly_flag
        return return_dict
