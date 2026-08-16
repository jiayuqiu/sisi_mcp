import sqlite3
from unittest.mock import patch

from mcp_conductor.entry import main_traffic_detect as traffic
from mcp_conductor.entry.main_setup_schema import SQL_CREATE_M_PIPE_ANOMALY_ROLL_PERCENTILE


def test_save_anomaly_results_persists_directional_ratios(tmp_path, monkeypatch):
    db_path = tmp_path / "results.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute(SQL_CREATE_M_PIPE_ANOMALY_ROLL_PERCENTILE)

    monkeypatch.setattr(traffic, "DB_PATH", db_path)
    pipe_result = {
        "pipe": "test_pipe",
        "run_date_id": 20260808,
        "anomaly_flag": 1,
        "quantile_10": 10.0,
        "quantile_25": 10.0,
        "quantile_75": 20.0,
        "quantile_90": 20.0,
        "anomaly_ratio": 0.7,
        "ratio_low": 0.6,
        "ratio_high": 0.1,
        "direction": "LOW",
        "duration_anomaly_flag": 1,
        "duration_quantile_10": 12.0,
        "duration_quantile_25": 12.0,
        "duration_quantile_75": 24.0,
        "duration_quantile_90": 24.0,
        "duration_anomaly_ratio": 0.5,
        "duration_ratio_low": 0.0,
        "duration_ratio_high": 0.5,
        "duration_direction": "HIGH",
        "duration_status": "OK",
        "regime": "BLOCKAGE",
    }
    port_result = {
        **pipe_result,
        "port": "test_pipe",
        "anomaly_flag": 0,
        "anomaly_ratio": 0.1,
        "ratio_low": 0.1,
        "ratio_high": 0.0,
        "direction": "NORMAL",
        "regime": "NORMAL",
    }
    traffic.save_anomaly_results({"pipe": [pipe_result], "port": [port_result]})

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT location_type, anomaly_ratio, ratio_low, ratio_high, direction,
                   duration_anomaly_flag, duration_anomaly_ratio,
                   duration_ratio_low, duration_ratio_high,
                   duration_direction, duration_status, regime
            FROM m_pipe_anomaly_roll_percentile
            WHERE pipe_name = 'test_pipe' AND date_id = 20260808
            ORDER BY location_type
            """
        ).fetchall()

    assert row == [
        ("pipe", 0.7, 0.6, 0.1, "LOW", 1, 0.5, 0.0, 0.5, "HIGH", "OK", "BLOCKAGE"),
        ("port", 0.1, 0.1, 0.0, "NORMAL", 1, 0.5, 0.0, 0.5, "HIGH", "OK", "NORMAL"),
    ]


def test_traffic_detect_persists_results_before_monitoring(tmp_path, monkeypatch):
    db_path = tmp_path / "results.sqlite"
    monkeypatch.setattr(traffic, "DB_PATH", db_path)
    detector_output = {"pipe": []}

    with patch.object(traffic, "rp_detect_engine", return_value=detector_output) as detect, patch.object(
        traffic, "save_anomaly_results"
    ) as save, patch.object(traffic, "monitor_roll_percentile") as monitor:
        traffic.traffic_detect("2026-07-26")

    detect.assert_called_once_with(run_date="2026-07-26")
    save.assert_called_once_with(detector_output)
    monitor.assert_called_once_with(
        db_path=db_path,
        end_date_id="2026-07-26",
        persist=True,
    )
