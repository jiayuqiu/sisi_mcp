import unittest
from unittest.mock import Mock, patch

import pandas as pd
from sqlalchemy import create_engine, text

from mcp_conductor.detector.roll_percentile import RollingPercentileDetector
from mcp_conductor.detector.detect_engine import (
    PIPE_TABLE,
    PORT_TABLE,
    classify_regime,
    detect_one_location,
    get_roll_percentile_parameters,
    run_detect,
    get_pipe_name_list,
    get_port_name_list,
    get_engine,
    rp_detect_engine
)
from mcp_conductor.resources.utils.sisi_dataclasses import ROLLING_PERCENTILE_FLAG as FLAG


class TestDetectEngine(unittest.TestCase):
    def setUp(self):
        self.engine = get_engine()
        self.detector = RollingPercentileDetector()

    def test_get_engine(self):
        get_engine()

    def test_parameter_lookup_uses_row_effective_on_run_date(self):
        engine = create_engine("sqlite://")
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE m_roll_percentile_parameter (
                    location_type TEXT, location_name TEXT, metric TEXT,
                    valid_from_date_id INTEGER, valid_to_date_id INTEGER,
                    lower_bound REAL, upper_bound REAL, anomaly_threshold REAL,
                    interval_days INTEGER, status TEXT
                )
            """))
            conn.execute(text("""
                INSERT INTO m_roll_percentile_parameter VALUES
                    ('pipe', 'test_pipe', 'ship_cnt', 20260101, 20260131, 1, 10, 0.2, 30, 'OK'),
                    ('pipe', 'test_pipe', 'ship_cnt', 20260201, NULL, 15, 25, 0.4, 14, 'OK')
            """))

        january = get_roll_percentile_parameters("pipe", "test_pipe", "ship_cnt", 20260131, engine)
        february = get_roll_percentile_parameters("pipe", "test_pipe", "ship_cnt", 20260201, engine)
        missing = get_roll_percentile_parameters("pipe", "test_pipe", "ship_cnt", 20251231, engine)

        self.assertEqual(january["lower_bound"], 1.0)
        self.assertEqual(february["lower_bound"], 15.0)
        self.assertEqual(february["interval_days"], 14)
        self.assertIsNone(missing)

    def test_regime_matrix_covers_key_count_duration_combinations(self):
        expected = {
            ("LOW", "LOW"): "AVOIDANCE",
            ("LOW", "HIGH"): "BLOCKAGE",
            ("HIGH", "HIGH"): "CONGESTION",
            ("HIGH", "LOW"): "HIGH_THROUGHPUT",
            ("NORMAL", "NORMAL"): "NORMAL",
            ("MIXED", "NORMAL"): "VOLATILE",
            ("UNKNOWN", "UNKNOWN"): "UNKNOWN",
        }
        for directions, regime in expected.items():
            with self.subTest(directions=directions):
                self.assertEqual(classify_regime(*directions), regime)

    def test_detect_one_location_returns_no_data_for_empty_signals(self):
        detector = Mock(spec=RollingPercentileDetector)

        result = detect_one_location(
            signals=pd.DataFrame(columns=["date_id", "ship_cnt"]),
            location_col_name="pipe",
            name_str="test_pipe",
            run_date_id=20260401,
            detector=detector,
            parameters={"status": "OK"},
        )

        self.assertEqual(result["pipe"], "test_pipe")
        self.assertEqual(result["run_date_id"], 20260401)
        self.assertEqual(result["anomaly_flag"], FLAG.NO_DATA)
        self.assertIsNone(result["quantile_10"])
        self.assertIsNone(result["quantile_25"])
        self.assertIsNone(result["quantile_75"])
        self.assertIsNone(result["quantile_90"])
        self.assertIsNone(result["ratio_low"])
        self.assertIsNone(result["ratio_high"])
        self.assertEqual(result["direction"], "UNKNOWN")
        self.assertIsNone(result["anomaly_ratio"])
        detector.detect.assert_not_called()

    def test_detect_one_location_delegates_to_detector(self):
        signals = pd.DataFrame(
            {"date_id": [20260401], "ship_cnt": [20]}
        )
        parameters = {"status": "OK", "lower_bound": 10, "upper_bound": 30}
        detector = Mock(spec=RollingPercentileDetector)
        detector.detect.return_value = {
            "anomaly_flag": FLAG.NORMAL,
            "quantile_10": 10.0,
            "quantile_25": 12.0,
            "quantile_75": 28.0,
            "quantile_90": 30.0,
            "ratio_low": 0.0,
            "ratio_high": 0.0,
            "direction": "NORMAL",
            "anomaly_ratio": 0.0,
        }

        result = detect_one_location(
            signals=signals,
            location_col_name="port",
            name_str="test_port",
            run_date_id=20260401,
            detector=detector,
            parameters=parameters,
        )

        detector.detect.assert_called_once_with(
            value=signals,
            location_col_name="port",
            name_str="test_port",
            run_date_id=20260401,
            parameters=parameters,
        )
        self.assertEqual(
            result,
            {
                "port": "test_port",
                "run_date_id": 20260401,
                "anomaly_flag": FLAG.NORMAL,
                "quantile_10": 10.0,
                "quantile_25": 12.0,
                "quantile_75": 28.0,
                "quantile_90": 30.0,
                "ratio_low": 0.0,
                "ratio_high": 0.0,
                "direction": "NORMAL",
                "anomaly_ratio": 0.0,
            },
        )

    def test_run_detect_loads_fitted_parameters_for_pipe_and_port(self):
        for app_type, source_table, name_col in (
            ("pipe", PIPE_TABLE, "pipe_name"),
            ("port", PORT_TABLE, "port_name"),
        ):
            with self.subTest(app_type=app_type):
                engine = create_engine("sqlite://")
                location_name = f"test_{app_type}"
                with engine.begin() as conn:
                    conn.execute(text(f"""
                        CREATE TABLE {source_table} (
                            {name_col} TEXT, date_id INTEGER, ship_cnt INTEGER,
                            duration REAL, detection_flag TEXT
                        )
                    """))
                    conn.execute(
                        text(f"""
                            INSERT INTO {source_table}
                                ({name_col}, date_id, ship_cnt, duration)
                            VALUES
                                (:name, 20260201, 20, 20),
                                (:name, 20260202, 20, 20),
                                (:name, 20260203, 30, 30),
                                (:name, 20260204, 30, 30)
                        """),
                        {"name": location_name},
                    )
                    conn.execute(text("""
                        CREATE TABLE m_roll_percentile_parameter (
                            location_type TEXT, location_name TEXT, metric TEXT,
                            valid_from_date_id INTEGER, valid_to_date_id INTEGER,
                            lower_bound REAL, upper_bound REAL, anomaly_threshold REAL,
                            interval_days INTEGER, status TEXT
                        )
                    """))
                    conn.execute(
                        text("""
                            INSERT INTO m_roll_percentile_parameter VALUES
                                (:location_type, :location_name, 'ship_cnt',
                                 20260201, NULL, 15, 25, 0.4, 4, 'OK'),
                                (:location_type, :location_name, 'duration',
                                 20260201, NULL, 15, 25, 0.4, 4, 'OK')
                        """),
                        {"location_type": app_type, "location_name": location_name},
                    )

                result = run_detect(
                    app_type=app_type,
                    app_detect_config={"name_list": [location_name], "table": source_table},
                    run_date_id=20260204,
                    start_date_id=20260201,
                    detector=self.detector,
                    engine=engine,
                )

                self.assertEqual(len(result), 1)
                self.assertEqual(result[0][app_type], location_name)
                self.assertEqual(result[0]["quantile_10"], 15.0)
                self.assertEqual(result[0]["quantile_90"], 25.0)
                self.assertEqual(result[0]["anomaly_ratio"], 0.5)
                self.assertEqual(result[0]["ratio_low"], 0.0)
                self.assertEqual(result[0]["ratio_high"], 0.5)
                self.assertEqual(result[0]["direction"], "HIGH")
                self.assertEqual(result[0]["anomaly_flag"], FLAG.ANOMALY)
                self.assertEqual(result[0]["duration_anomaly_flag"], FLAG.ANOMALY)
                self.assertEqual(result[0]["duration_direction"], "HIGH")
                self.assertEqual(result[0]["duration_status"], "OK")
                self.assertEqual(result[0]["regime"], "CONGESTION")

    def test_rp_detect_engine(self):
        engine = Mock()
        pipe_result = [{"pipe": "test_pipe"}]
        port_result = [{"port": "test_port"}]
        with (
            patch("mcp_conductor.detector.detect_engine.get_engine", return_value=engine),
            patch("mcp_conductor.detector.detect_engine.get_pipe_name_list", return_value=["test_pipe"]),
            patch("mcp_conductor.detector.detect_engine.get_port_name_list", return_value=["test_port"]),
            patch(
                "mcp_conductor.detector.detect_engine.run_detect",
                side_effect=[pipe_result, port_result],
            ) as run_detect_mock,
        ):
            app_detect_results = rp_detect_engine(run_date="2026-04-01")

        self.assertEqual(app_detect_results, {"pipe": pipe_result, "port": port_result})
        self.assertEqual(run_detect_mock.call_count, 2)
