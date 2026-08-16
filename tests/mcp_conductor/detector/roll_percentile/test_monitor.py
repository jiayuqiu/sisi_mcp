import sqlite3

import pytest

from mcp_conductor.detector.roll_percentile.monitor import (
    STATUS_ELEVATED,
    STATUS_NO_DATA,
    STATUS_OK,
    STATUS_PARAMETER_UNUSABLE,
    build_monitor_snapshot,
    persist_monitor_snapshot,
)
from mcp_conductor.entry.main_setup_schema import (
    SQL_CREATE_M_PIPE_ANOMALY_ROLL_PERCENTILE,
    SQL_CREATE_M_ROLL_PERCENTILE_MONITOR,
    SQL_CREATE_M_ROLL_PERCENTILE_PARAMETER,
    SQL_CREATE_SHIP_CNT_IN_PIPE,
    SQL_CREATE_SHIP_CNT_IN_PORT,
)


def _monitor_store(tmp_path):
    db_path = tmp_path / "monitor.sqlite"
    conn = sqlite3.connect(db_path)
    for statement in (
        SQL_CREATE_SHIP_CNT_IN_PIPE,
        SQL_CREATE_SHIP_CNT_IN_PORT,
        SQL_CREATE_M_PIPE_ANOMALY_ROLL_PERCENTILE,
        SQL_CREATE_M_ROLL_PERCENTILE_PARAMETER,
        SQL_CREATE_M_ROLL_PERCENTILE_MONITOR,
    ):
        conn.execute(statement)

    conn.executemany(
        "INSERT INTO ship_cnt_in_pipe (pipe_name, date_id) VALUES (?, 20260701)",
        [("Pipe A",), ("Pipe C",)],
    )
    conn.execute(
        "INSERT INTO ship_cnt_in_port (port_name, date_id) VALUES ('Port B', 20260701)"
    )

    parameters = [
        ("pipe", "Pipe A", "ship_cnt", "OK"),
        ("pipe", "Pipe A", "duration", "OK"),
        ("pipe", "Pipe C", "ship_cnt", "OK"),
        ("pipe", "Pipe C", "duration", "OK"),
        ("port", "Port B", "ship_cnt", "INSUFFICIENT"),
        ("port", "Port B", "duration", "INSUFFICIENT"),
    ]
    conn.executemany(
        """
        INSERT INTO m_roll_percentile_parameter (
            location_type, location_name, metric, valid_from_date_id,
            lower_bound, upper_bound, anomaly_threshold, interval_days, status,
            fit_method, calibration_target_flag_rate, is_locked
        ) VALUES (?, ?, ?, 20260701, 1, 10, 0.2, 30, ?,
                  'percentile_10_90_holdout', 0.05, 0)
        """,
        parameters,
    )

    results = [
        (20260630, 0, "NORMAL", 0, "NORMAL", "OK"),
        (20260701, 0, "NORMAL", 0, "NORMAL", "OK"),
        (20260702, 1, "LOW", 1, "HIGH", "OK"),
        (20260703, 1, "HIGH", 2, "UNKNOWN", "NO_DATA"),
        (20260704, 0, "NORMAL", 0, "NORMAL", "OK"),
    ]
    conn.executemany(
        """
        INSERT INTO m_pipe_anomaly_roll_percentile (
            location_type, pipe_name, date_id, anomaly_flag, direction,
            duration_anomaly_flag, duration_direction, duration_status
        ) VALUES ('pipe', 'Pipe A', ?, ?, ?, ?, ?, ?)
        """,
        results,
    )
    conn.commit()
    return conn


def _row(snapshots, location_name, metric, direction, location_type=None):
    return next(
        row
        for row in snapshots
        if row["location_name"] == location_name
        and row["metric"] == metric
        and row["direction"] == direction
        and (location_type is None or row["location_type"] == location_type)
    )


def test_monitor_calculates_rates_by_metric_and_direction(tmp_path):
    conn = _monitor_store(tmp_path)
    try:
        snapshots = build_monitor_snapshot(
            conn,
            end_date_id=20260704,
            window_days=30,
            min_eligible_samples=3,
        )
    finally:
        conn.close()

    count_any = _row(snapshots, "Pipe A", "ship_cnt", "ANY")
    assert count_any["window_start_date_id"] == 20260701
    assert count_any["observation_count"] == 4
    assert count_any["eligible_count"] == 4
    assert count_any["flagged_count"] == 2
    assert count_any["flag_rate"] == 0.5
    assert count_any["status"] == STATUS_ELEVATED

    assert _row(snapshots, "Pipe A", "ship_cnt", "LOW")["flag_rate"] == 0.25
    assert _row(snapshots, "Pipe A", "ship_cnt", "HIGH")["flag_rate"] == 0.25
    assert _row(snapshots, "Pipe A", "ship_cnt", "MIXED")["status"] == STATUS_OK

    duration_any = _row(snapshots, "Pipe A", "duration", "ANY")
    assert duration_any["observation_count"] == 4
    assert duration_any["eligible_count"] == 3
    assert duration_any["flagged_count"] == 1
    assert duration_any["flag_rate"] == pytest.approx(1 / 3)
    assert duration_any["status"] == STATUS_ELEVATED


def test_monitor_reports_unusable_parameters_and_missing_results(tmp_path):
    conn = _monitor_store(tmp_path)
    try:
        snapshots = build_monitor_snapshot(conn, 20260704, min_eligible_samples=3)
    finally:
        conn.close()

    assert _row(snapshots, "Port B", "ship_cnt", "ANY")["status"] == STATUS_PARAMETER_UNUSABLE
    assert _row(snapshots, "Pipe C", "ship_cnt", "ANY")["status"] == STATUS_NO_DATA


def test_monitor_persistence_is_idempotent(tmp_path):
    conn = _monitor_store(tmp_path)
    try:
        snapshots = build_monitor_snapshot(conn, 20260704, min_eligible_samples=3)
        persist_monitor_snapshot(conn, snapshots)
        persist_monitor_snapshot(conn, snapshots)
        count = conn.execute("SELECT COUNT(*) FROM m_roll_percentile_monitor").fetchone()[0]
    finally:
        conn.close()

    assert count == 24


def test_monitor_keeps_same_name_pipe_and_port_separate(tmp_path):
    conn = _monitor_store(tmp_path)
    try:
        conn.execute(
            "INSERT INTO ship_cnt_in_port (port_name, date_id) VALUES ('Pipe A', 20260702)"
        )
        conn.execute(
            """
            INSERT INTO m_roll_percentile_parameter (
                location_type, location_name, metric, valid_from_date_id,
                lower_bound, upper_bound, anomaly_threshold, interval_days, status,
                fit_method, calibration_target_flag_rate, is_locked
            ) VALUES ('port', 'Pipe A', 'ship_cnt', 20260701,
                      1, 10, 0.2, 30, 'OK', 'percentile_10_90_holdout', 0.05, 0)
            """
        )
        conn.execute(
            """
            INSERT INTO m_pipe_anomaly_roll_percentile (
                location_type, pipe_name, date_id, anomaly_flag, direction
            ) VALUES ('port', 'Pipe A', 20260704, 1, 'HIGH')
            """
        )

        snapshots = build_monitor_snapshot(conn, 20260704, min_eligible_samples=1)

        pipe_row = _row(snapshots, "Pipe A", "ship_cnt", "ANY", "pipe")
        port_row = _row(snapshots, "Pipe A", "ship_cnt", "ANY", "port")
        assert pipe_row["observation_count"] == 4
        assert pipe_row["flagged_count"] == 2
        assert port_row["observation_count"] == 1
        assert port_row["flagged_count"] == 1
    finally:
        conn.close()
