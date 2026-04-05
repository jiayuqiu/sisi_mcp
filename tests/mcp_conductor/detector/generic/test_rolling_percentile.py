import unittest
import numpy as np
import pandas as pd

from mcp_conductor.detector.generic.rolling_percentile import RollingPercentileDetector
from mcp_conductor.resources.utils.sisi_dataclasses import ROLLING_PERCENTILE_FLAG as FLAG


def _make_df(date_ids, ship_cnts) -> pd.DataFrame:
    return pd.DataFrame({"date_id": date_ids, "ship_cnt": ship_cnts})


# 100-day baseline: ship_cnt 10–109, date_id 1–100
# p10 ≈ 19.9,  p90 ≈ 99.1
_BASELINE = _make_df(range(1, 101), range(10, 110))


class TestRollingPercentileDetector(unittest.TestCase):

    # ------------------------------------------------------------------
    # Init / config
    # ------------------------------------------------------------------

    def test_default_threshold(self):
        d = RollingPercentileDetector()
        self.assertEqual(d.anomaly_percentage_threshold, 0.5)

    def test_custom_threshold(self):
        d = RollingPercentileDetector({"anomaly_percentage_threshold": 0.3})
        self.assertEqual(d.anomaly_percentage_threshold, 0.3)

    # ------------------------------------------------------------------
    # Return structure
    # ------------------------------------------------------------------

    def test_return_dict_has_required_keys(self):
        recent = _make_df(range(101, 108), [55] * 7)
        df = pd.concat([_BASELINE, recent], ignore_index=True)

        d = RollingPercentileDetector()
        result = d.detect(df, pipe_name="马六甲海峡", run_date_id=20240407)
        self.assertIsInstance(result, dict)
        self.assertIn("anomaly_flag", result)
        self.assertIn("quantile_10", result)
        self.assertIn("quantile_90", result)
        self.assertIn("anomaly_ratio", result)

    def test_quantile_values_are_reasonable(self):
        recent = _make_df(range(101, 108), [55] * 7)
        df = pd.concat([_BASELINE, recent], ignore_index=True)

        d = RollingPercentileDetector()
        result = d.detect(df, pipe_name="马六甲海峡", run_date_id=20240407)
        self.assertAlmostEqual(result["quantile_10"], 19.9, delta=1.0)
        self.assertAlmostEqual(result["quantile_90"], 99.1, delta=1.0)

    # ------------------------------------------------------------------
    # Normal traffic
    # ------------------------------------------------------------------

    def test_normal_recent_returns_normal(self):
        # 7 recent days all within [p10, p90]
        recent = _make_df(range(101, 108), [55] * 7)
        df = pd.concat([_BASELINE, recent], ignore_index=True)

        d = RollingPercentileDetector()
        result = d.detect(df, pipe_name="马六甲海峡", run_date_id=20240407)
        self.assertEqual(result["anomaly_flag"], FLAG.NORMAL)
        self.assertEqual(result["anomaly_ratio"], 0.0)

    # ------------------------------------------------------------------
    # Too busy
    # ------------------------------------------------------------------

    def test_high_recent_traffic_returns_anomaly(self):
        # 7 recent days all above p90 (150 >> 99.1)
        recent = _make_df(range(101, 108), [150] * 7)
        df = pd.concat([_BASELINE, recent], ignore_index=True)

        d = RollingPercentileDetector()
        result = d.detect(df, pipe_name="马六甲海峡", run_date_id=20240407)
        self.assertEqual(result["anomaly_flag"], FLAG.ANOMALY)
        self.assertEqual(result["anomaly_ratio"], 1.0)

    # ------------------------------------------------------------------
    # Too vacant
    # ------------------------------------------------------------------

    def test_low_recent_traffic_returns_anomaly(self):
        # 7 recent days all below p10 (5 << 19.9)
        recent = _make_df(range(101, 108), [5] * 7)
        df = pd.concat([_BASELINE, recent], ignore_index=True)

        d = RollingPercentileDetector()
        result = d.detect(df, pipe_name="马六甲海峡", run_date_id=20240407)
        self.assertEqual(result["anomaly_flag"], FLAG.ANOMALY)

    # ------------------------------------------------------------------
    # Threshold boundary
    # ------------------------------------------------------------------

    def test_below_threshold_returns_normal(self):
        # 3 out of 7 anomalous → ratio 3/7 ≈ 0.43 < 0.5 → NORMAL
        cnts = [150, 150, 150, 55, 55, 55, 55]  # 3 high, 4 normal
        recent = _make_df(range(101, 108), cnts)
        df = pd.concat([_BASELINE, recent], ignore_index=True)

        d = RollingPercentileDetector()
        result = d.detect(df, pipe_name="马六甲海峡", run_date_id=20240407)
        self.assertEqual(result["anomaly_flag"], FLAG.NORMAL)
        self.assertAlmostEqual(result["anomaly_ratio"], 3 / 7, places=4)

    def test_above_threshold_returns_anomaly(self):
        # 4 out of 7 anomalous → ratio 4/7 ≈ 0.57 > 0.5 → ANOMALY
        cnts = [150, 150, 150, 150, 55, 55, 55]  # 4 high, 3 normal
        recent = _make_df(range(101, 108), cnts)
        df = pd.concat([_BASELINE, recent], ignore_index=True)

        d = RollingPercentileDetector()
        result = d.detect(df, pipe_name="马六甲海峡", run_date_id=20240407)
        self.assertEqual(result["anomaly_flag"], FLAG.ANOMALY)
        self.assertAlmostEqual(result["anomaly_ratio"], 4 / 7, places=4)

    # ------------------------------------------------------------------
    # interval_days: only the most recent N rows are evaluated
    # ------------------------------------------------------------------

    def test_old_anomalies_ignored_when_recent_is_normal(self):
        # days 1-100: baseline
        # days 101-107: anomalous (old)
        # days 108-114: normal (recent, interval_days=7)
        old_anomaly = _make_df(range(101, 108), [150] * 7)
        recent_normal = _make_df(range(108, 115), [55] * 7)
        df = pd.concat([_BASELINE, old_anomaly, recent_normal], ignore_index=True)

        d = RollingPercentileDetector()
        # interval_days=7 picks days 108-114 (normal) → NORMAL
        result = d.detect(df, pipe_name="马六甲海峡", run_date_id=20240414, interval_days=7)
        self.assertEqual(result["anomaly_flag"], FLAG.NORMAL)

    def test_interval_days_parameter_respected(self):
        # days 101-107: normal; days 108-114: all anomalous
        normal_block = _make_df(range(101, 108), [55] * 7)
        anomaly_block = _make_df(range(108, 115), [150] * 7)
        df = pd.concat([_BASELINE, normal_block, anomaly_block], ignore_index=True)

        d = RollingPercentileDetector()
        # interval_days=7 → only anomaly_block evaluated → ANOMALY
        result = d.detect(df, pipe_name="马六甲海峡", run_date_id=20240414, interval_days=7)
        self.assertEqual(result["anomaly_flag"], FLAG.ANOMALY)
        # interval_days=14 → both blocks evaluated → 7/14 = 0.5, not > 0.5 → NORMAL
        result = d.detect(df, pipe_name="马六甲海峡", run_date_id=20240414, interval_days=14)
        self.assertEqual(result["anomaly_flag"], FLAG.NORMAL)

    # ------------------------------------------------------------------
    # Mixed busy / vacant in the same window
    # ------------------------------------------------------------------

    def test_mixed_high_and_low_anomalies(self):
        # 4 very high + 3 very low → all 7 are anomalies → ANOMALY
        cnts = [150, 150, 150, 150, 5, 5, 5]
        recent = _make_df(range(101, 108), cnts)
        df = pd.concat([_BASELINE, recent], ignore_index=True)

        d = RollingPercentileDetector()
        result = d.detect(df, pipe_name="马六甲海峡", run_date_id=20240407)
        self.assertEqual(result["anomaly_flag"], FLAG.ANOMALY)

    # ------------------------------------------------------------------
    # Edge cases: NO_DATA / FLAT_DATA
    # ------------------------------------------------------------------

    def test_all_zero_returns_no_data(self):
        df = _make_df(range(1, 101), [0] * 100)
        d = RollingPercentileDetector()
        result = d.detect(df, pipe_name="马六甲海峡", run_date_id=20240407)
        self.assertEqual(result["anomaly_flag"], FLAG.NO_DATA)

    def test_flat_data_returns_flat_data(self):
        # all same non-zero value → p10 == p90
        df = _make_df(range(1, 101), [42] * 100)
        d = RollingPercentileDetector()
        result = d.detect(df, pipe_name="马六甲海峡", run_date_id=20240407)
        self.assertEqual(result["anomaly_flag"], FLAG.FLAT_DATA)

    def test_no_data_and_flat_data_have_no_ratio(self):
        # early-exit paths should not include anomaly_ratio
        d = RollingPercentileDetector()

        result_zero = d.detect(_make_df(range(1, 101), [0] * 100),
                               pipe_name="test", run_date_id=20240407)
        self.assertNotIn("anomaly_ratio", result_zero)

        result_flat = d.detect(_make_df(range(1, 101), [42] * 100),
                               pipe_name="test", run_date_id=20240407)
        self.assertNotIn("anomaly_ratio", result_flat)
