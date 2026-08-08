import unittest

import pandas as pd

from mcp_conductor.detector.generic.rolling_percentile import RollingPercentileDetector
from mcp_conductor.resources.utils.sisi_dataclasses import ROLLING_PERCENTILE_FLAG as FLAG


def _make_df(date_ids, ship_cnts) -> pd.DataFrame:
    return pd.DataFrame({"date_id": date_ids, "ship_cnt": ship_cnts})


def _ok_parameters(**overrides) -> dict:
    parameters = {
        "lower_bound": 15.0,
        "upper_bound": 25.0,
        "anomaly_threshold": 0.5,
        "interval_days": 4,
        "status": "OK",
    }
    parameters.update(overrides)
    return parameters


class TestRollingPercentileDetector(unittest.TestCase):
    def setUp(self):
        self.detector = RollingPercentileDetector()

    def detect(self, value, parameters):
        return self.detector.detect(
            value=value,
            location_col_name="pipe_name",
            name_str="霍尔木兹海峡",
            run_date_id=20260722,
            parameters=parameters,
        )

    def test_uses_fitted_bounds_instead_of_history(self):
        # The old implementation would derive a much wider scoring band from these
        # historical values. The stored manual override must be authoritative.
        history = _make_df(range(1, 101), range(1, 101))
        recent = _make_df(range(101, 105), [20, 20, 30, 30])
        result = self.detect(pd.concat([history, recent], ignore_index=True), _ok_parameters())

        self.assertEqual(result["quantile_10"], 15.0)
        self.assertEqual(result["quantile_90"], 25.0)
        self.assertEqual(result["anomaly_ratio"], 0.5)
        self.assertEqual(result["anomaly_flag"], FLAG.NORMAL)  # threshold is strict: ratio is not greater

    def test_uses_stored_interval_and_threshold(self):
        signals = _make_df(range(1, 6), [20, 20, 20, 30, 30])
        result = self.detect(
            signals,
            _ok_parameters(interval_days=5, anomaly_threshold=0.3),
        )

        self.assertEqual(result["anomaly_ratio"], 0.4)
        self.assertEqual(result["anomaly_flag"], FLAG.ANOMALY)

    def test_non_ok_fitted_status_short_circuits(self):
        signals = _make_df(range(1, 5), [100, 100, 100, 100])
        for status, flag in (
            ("NO_DATA", FLAG.NO_DATA),
            ("FLAT", FLAG.FLAT_DATA),
            ("INSUFFICIENT", FLAG.INSUFFICIENT_DATA),
        ):
            with self.subTest(status=status):
                result = self.detect(signals, _ok_parameters(status=status, lower_bound=None, upper_bound=None))
                self.assertEqual(result["anomaly_flag"], flag)
                self.assertNotIn("anomaly_ratio", result)

    def test_missing_fitted_row_returns_no_data(self):
        result = self.detect(_make_df(range(1, 5), [20, 20, 20, 20]), None)
        self.assertEqual(result["anomaly_flag"], FLAG.NO_DATA)

    def test_latest_zero_remains_an_anomaly(self):
        result = self.detect(_make_df(range(1, 5), [20, 20, 20, 0]), _ok_parameters())
        self.assertEqual(result["anomaly_flag"], FLAG.ANOMALY)
        self.assertEqual(result["anomaly_ratio"], -1.0)
