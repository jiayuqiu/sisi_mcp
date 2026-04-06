import numpy as np
from typing import Dict, Any

from pandas import DataFrame

from mcp_conductor.detector.generic.base_detector import BaseDetector
from mcp_conductor.resources.utils.logger import get_logger
from mcp_conductor.resources.utils.sisi_dataclasses import ROLLING_PERCENTILE_FLAG as FLAG

logger = get_logger(__name__)


class RollingPercentileDetector(BaseDetector):
    """
    Detects whether a strait's recent traffic is anomalous using percentile bounds.

    Strategy:
        1. Compute p10 and p90 from the full historical ship count data.
        2. Inspect the most recent `interval_days` days.
        3. Count how many of those days fall outside [p10, p90].
        4. If the anomaly ratio exceeds `anomaly_percentage_threshold`, the strait
           is considered anomalous (too busy or too vacant).

    Config keys:
        anomaly_percentage_threshold (float): ratio (0–1) of recent days that must
                                              be outliers to trigger an alert.
                                              Default: 0.5 (50 % of interval_days).
    """

    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.window: int = 365  # get a year data to calculate 10 and 90 percentile value.
        self.anomaly_percentage_threshold = float(self.config.get("anomaly_percentage_threshold", 0.5))

    def detect(
        self,
        value: DataFrame,
        pipe_name: str,
        run_date_id: int,
        interval_days: int = 30
    ) -> dict:
        """
        Args:
            value        : full historical DataFrame for one strait,
                           must contain columns [date_id, ship_cnt].
            pipe_name    : strait name (reserved for future use / logging).
            run_date_id  : reference date in YYYYMMDD (reserved for future use).
            interval_days: number of most-recent days to evaluate. Default 30.

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
        # init return value
        return_dict = {}

        # derive p10 / p90 bounds from the entire historical record
        quantile_10 = np.percentile(value["ship_cnt"], 10)
        quantile_25 = np.percentile(value["ship_cnt"], 25)
        quantile_75 = np.percentile(value["ship_cnt"], 75)
        quantile_90 = np.percentile(value["ship_cnt"], 90)
        return_dict["quantile_10"] = quantile_10
        return_dict["quantile_25"] = quantile_25
        return_dict["quantile_75"] = quantile_75
        return_dict["quantile_90"] = quantile_90
        if (quantile_10 == 0) and (quantile_90 == 0):
            logger.warning(f"{pipe_name} on {run_date_id} has no recent a year traffic data.")
            return_dict["anomaly_flag"] = FLAG.NO_DATA
            
            return return_dict
        elif quantile_10 == quantile_90:
            logger.warning(f"{pipe_name} on {run_date_id}, recent a year data with "
                           f"same 10% and 90% percentile value - {quantile_10}.")
            return_dict["anomaly_flag"] = FLAG.FLAT_DATA
            return return_dict
        elif 0 <= quantile_90 <= 3:
            logger.warning(f"{pipe_name} on {run_date_id}, both ofquantile_90 < 3. "
                           f"too small to detect.")
            return_dict["anomaly_flag"] = FLAG.INSUFFICIENT_DATA
            return return_dict
        # elif (quantile_90 > 3) and (quantile_10 == 0):
        #     logger.warning(f"{pipe_name} on {run_date_id}, quantile_10 is 0, set quantile_10 = 3")
        #     quantile_10 = 3

        # isolate the most recent `interval_days` rows
        recent = value.sort_values(by=["date_id"], ascending=False).head(interval_days)

        # count days whose ship_cnt falls outside [p10, p90]
        anomaly_cnt = 0
        for idx, row in recent.iterrows():
            if (row["ship_cnt"] < quantile_25) or (row["ship_cnt"] > quantile_75):
                anomaly_cnt += 1

        # flag as anomalous when the outlier ratio exceeds the threshold
        anomaly_ratio = anomaly_cnt / interval_days
        anomaly_flag = FLAG.ANOMALY if anomaly_ratio > self.anomaly_percentage_threshold else FLAG.NORMAL
        return_dict["anomaly_ratio"] = anomaly_ratio
        return_dict["anomaly_flag"] = anomaly_flag
        return return_dict
