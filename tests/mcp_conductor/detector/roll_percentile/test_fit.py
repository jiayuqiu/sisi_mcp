import sqlite3
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import create_engine

from mcp_conductor.detector.roll_percentile.fit import (
    LOCATION_FIT_START_FLOORS,
    STATUS_FLAT,
    STATUS_INSUFFICIENT,
    STATUS_NO_DATA,
    STATUS_OK,
    fit_one_location,
    fit_roll_percentile_parameters,
    resolve_fit_start,
)
from mcp_conductor.entry.main_setup_schema import SQL_CREATE_M_ROLL_PERCENTILE_PARAMETER


def _history(ship_cnt: list[float], duration: list[float] | None = None) -> pd.DataFrame:
    if duration is None:
        duration = [float(value) for value in ship_cnt]
    return pd.DataFrame(
        {
            "date_id": range(1, len(ship_cnt) + 1),
            "ship_cnt": ship_cnt,
            "duration": duration,
        }
    )


def test_fit_one_location_excludes_zeros_and_uses_recent_records():
    history = _history([0] * 5 + list(range(1, 101)) + [0] * 5)

    result = fit_one_location(history, metric="ship_cnt", recent_records=90)

    # The newest 30 raw observations are validation data, including the five zeros.
    # Bounds use the latest 60 positive observations before that block.
    training = np.arange(16, 76)
    assert result["status"] == STATUS_OK
    assert result["fit_sample_size"] == 90
    assert result["fit_start_date_id"] == 21
    assert result["fit_end_date_id"] == 110
    assert result["training_sample_size"] == 60
    assert result["calibration_sample_size"] == 30
    assert result["calibration_start_date_id"] == 81
    assert result["calibration_end_date_id"] == 110
    assert result["lower_bound"] == np.percentile(training, 10)
    assert result["upper_bound"] == np.percentile(training, 90)


def test_ship_count_validation_keeps_zeros_but_bounds_do_not():
    training_values = [5 + offset % 10 for offset in range(90)]
    normal = fit_one_location(
        _history(training_values + [10] * 30),
        metric="ship_cnt",
        recent_records=120,
    )
    zeros = fit_one_location(
        _history(training_values + [0] * 15 + [10] * 15),
        metric="ship_cnt",
        recent_records=120,
    )

    assert normal["status"] == STATUS_OK
    assert zeros["status"] == STATUS_OK
    assert zeros["lower_bound"] == normal["lower_bound"]
    assert zeros["upper_bound"] == normal["upper_bound"]
    assert zeros["anomaly_threshold"] > normal["anomaly_threshold"]
    assert zeros["calibration_start_date_id"] == 91
    assert zeros["calibration_end_date_id"] == 120
    assert zeros["calibration_sample_size"] == 30
    assert zeros["calibration_flag_rate"] is not None


def test_ship_count_validation_rate_preserves_latest_zero_rule():
    result = fit_one_location(
        _history([15, 20, 25] * 30 + [20] * 29 + [0]),
        metric="ship_cnt",
        recent_records=120,
    )

    # One zero is only 1/30 of the ratio, below the 0.20 threshold floor, but live
    # serving always flags a latest zero. Validation reports the same 1/30 flag rate.
    assert result["status"] == STATUS_OK
    assert result["anomaly_threshold"] == 0.2
    assert result["calibration_flag_rate"] == 1 / 30


def test_fit_one_location_assigns_history_statuses():
    cases = (
        (_history([0] * 60), STATUS_NO_DATA),
        (_history(list(range(10, 99))), STATUS_INSUFFICIENT),
        (_history([10] * 90), STATUS_FLAT),
        (_history([1, 2, 3] * 30), STATUS_INSUFFICIENT),
    )

    for history, expected_status in cases:
        result = fit_one_location(history, metric="ship_cnt")
        assert result["status"] == expected_status
        assert result["lower_bound"] is None
        assert result["upper_bound"] is None


def test_duration_fit_rejects_locations_with_too_few_ships():
    result = fit_one_location(
        _history([2] * 90, duration=list(range(10, 100))),
        metric="duration",
    )

    assert result["status"] == STATUS_INSUFFICIENT
    assert result["lower_bound"] is None
    assert result["upper_bound"] is None


def test_duration_reliability_gate_includes_the_holdout_period():
    result = fit_one_location(
        _history(
            [2] * 29 + [3] * 31 + [1] * 30,
            duration=list(range(10, 100)),
        ),
        metric="duration",
    )

    assert result["status"] == STATUS_INSUFFICIENT


def test_duration_fit_excludes_zero_ship_days_and_accepts_reliable_data():
    result = fit_one_location(
        _history(
            [3] * 95 + [0] * 10,
            duration=list(range(10, 105)) + [999] * 10,
        ),
        metric="duration",
        recent_records=90,
    )

    training = np.arange(15, 75)
    assert result["status"] == STATUS_OK
    assert result["fit_sample_size"] == 90
    assert result["lower_bound"] == np.percentile(training, 10)
    assert result["upper_bound"] == np.percentile(training, 90)


def test_holdout_does_not_influence_fitted_bounds_and_changes_threshold():
    training_values = [5 + offset % 10 for offset in range(90)]
    normal = fit_one_location(
        _history(training_values + [10] * 30),
        metric="ship_cnt",
        recent_records=120,
    )
    shifted = fit_one_location(
        _history(training_values + [100] * 30),
        metric="ship_cnt",
        recent_records=120,
    )

    assert normal["status"] == STATUS_OK
    assert shifted["status"] == STATUS_OK
    assert normal["lower_bound"] == shifted["lower_bound"]
    assert normal["upper_bound"] == shifted["upper_bound"]
    assert normal["anomaly_threshold"] < shifted["anomaly_threshold"]
    assert shifted["anomaly_threshold"] == 0.8
    assert shifted["calibration_start_date_id"] == 91
    assert shifted["calibration_end_date_id"] == 120
    assert shifted["calibration_sample_size"] == 30
    assert shifted["calibration_flag_rate"] is not None


def test_fit_requires_enough_training_and_holdout_observations():
    result = fit_one_location(_history(list(range(10, 99))), metric="ship_cnt")

    assert result["status"] == STATUS_INSUFFICIENT
    assert result["fit_sample_size"] == 89


def test_sparse_port_production_floors_are_explicit():
    assert LOCATION_FIT_START_FLOORS == {
        ("port", "南沙港"): 20260101,
        ("port", "阿布扎比港"): 20260101,
        ("port", "杰贝阿里"): 20260101,
        ("port", "德班港"): 20260101,
    }


def test_location_floor_wins_unless_a_later_global_floor_is_requested():
    assert resolve_fit_start("port", "南沙港", 20260725) == 20260101
    assert resolve_fit_start("port", "南沙港", 20260725, 20250101) == 20260101
    assert resolve_fit_start("port", "南沙港", 20260725, 20260401) == 20260401
    assert resolve_fit_start("port", "普通港", 20260725, 20250101) == 20250101


def test_location_floor_does_not_blank_historical_as_of_fits():
    assert resolve_fit_start("port", "南沙港", 20251231) is None


def _create_fit_store(tmp_path):
    db_path = tmp_path / "fit.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE ship_cnt_in_pipe (
            pipe_name TEXT,
            date_id INTEGER,
            ship_cnt INTEGER,
            duration REAL,
            detection_flag TEXT,
            PRIMARY KEY (pipe_name, date_id)
        )
        """
    )
    conn.execute(SQL_CREATE_M_ROLL_PERCENTILE_PARAMETER)

    start = date(2026, 1, 1)
    rows = []
    for offset in range(151):
        day = start + timedelta(days=offset)
        rows.append(
            (
                "fixture_pipe",
                int(day.strftime("%Y%m%d")),
                10 + offset % 20,
                100.0 + offset % 30,
            )
        )
    conn.executemany(
        """
        INSERT INTO ship_cnt_in_pipe (pipe_name, date_id, ship_cnt, duration)
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    engine = create_engine(f"sqlite:///{db_path}")
    return conn, engine


def _fit(conn, engine, as_of_date_id: int):
    return fit_roll_percentile_parameters(
        location_type="pipe",
        metric="ship_cnt",
        recent_records=90,
        as_of_date_id=as_of_date_id,
        engine=engine,
        conn=conn,
    )


def test_persistence_versions_rows_and_is_idempotent(tmp_path):
    conn, engine = _create_fit_store(tmp_path)
    try:
        _fit(conn, engine, 20260331)
        _fit(conn, engine, 20260430)
        _fit(conn, engine, 20260430)

        rows = conn.execute(
            """
            SELECT valid_from_date_id, valid_to_date_id
            FROM m_roll_percentile_parameter
            ORDER BY valid_from_date_id
            """
        ).fetchall()
        assert rows == [(20260401, 20260430), (20260501, None)]
    finally:
        engine.dispose()
        conn.close()


def test_persistence_preserves_locked_manual_row(tmp_path):
    conn, engine = _create_fit_store(tmp_path)
    try:
        _fit(conn, engine, 20260331)
        conn.execute(
            """
            UPDATE m_roll_percentile_parameter
            SET lower_bound = 15, upper_bound = 25,
                fit_method = 'manual', is_locked = 1
            WHERE valid_to_date_id IS NULL
            """
        )
        conn.commit()

        result = _fit(conn, engine, 20260430)
        stored = conn.execute(
            """
            SELECT COUNT(*), lower_bound, upper_bound, fit_method, is_locked
            FROM m_roll_percentile_parameter
            """
        ).fetchone()

        assert result == [
            {
                "location_type": "pipe",
                "location_name": "fixture_pipe",
                "metric": "ship_cnt",
                "skipped": "locked",
            }
        ]
        assert stored == (1, 15.0, 25.0, "manual", 1)
    finally:
        engine.dispose()
        conn.close()


def test_persistence_can_insert_historical_version_before_future_version(tmp_path):
    conn, engine = _create_fit_store(tmp_path)
    try:
        _fit(conn, engine, 20260430)
        _fit(conn, engine, 20260331)

        rows = conn.execute(
            """
            SELECT valid_from_date_id, valid_to_date_id
            FROM m_roll_percentile_parameter
            ORDER BY valid_from_date_id
            """
        ).fetchall()

        assert rows == [(20260401, 20260430), (20260501, None)]
    finally:
        engine.dispose()
        conn.close()


def test_future_manual_lock_does_not_block_earlier_historical_fit(tmp_path):
    conn, engine = _create_fit_store(tmp_path)
    try:
        _fit(conn, engine, 20260430)
        conn.execute(
            """
            UPDATE m_roll_percentile_parameter
            SET lower_bound = 15, upper_bound = 25,
                fit_method = 'manual', is_locked = 1
            WHERE valid_from_date_id = 20260501
            """
        )
        conn.commit()

        result = _fit(conn, engine, 20260331)
        rows = conn.execute(
            """
            SELECT valid_from_date_id, valid_to_date_id, fit_method, is_locked
            FROM m_roll_percentile_parameter
            ORDER BY valid_from_date_id
            """
        ).fetchall()

        assert "skipped" not in result[0]
        assert rows == [
            (20260401, 20260430, "percentile_10_90_holdout", 0),
            (20260501, None, "manual", 1),
        ]
    finally:
        engine.dispose()
        conn.close()
