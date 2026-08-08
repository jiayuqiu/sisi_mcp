import sqlite3
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import create_engine

from mcp_conductor.detector.roll_percentile.fit import (
    STATUS_FLAT,
    STATUS_INSUFFICIENT,
    STATUS_NO_DATA,
    STATUS_OK,
    fit_one_location,
    fit_roll_percentile_parameters,
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
    history = _history([0] * 5 + list(range(1, 71)) + [0] * 5)

    result = fit_one_location(history, metric="ship_cnt", recent_records=60)

    retained = np.arange(11, 71)
    assert result["status"] == STATUS_OK
    assert result["fit_sample_size"] == 60
    assert result["fit_start_date_id"] == 16
    assert result["fit_end_date_id"] == 75
    assert result["lower_bound"] == np.percentile(retained, 10)
    assert result["upper_bound"] == np.percentile(retained, 90)


def test_fit_one_location_assigns_history_statuses():
    cases = (
        (_history([0] * 60), STATUS_NO_DATA),
        (_history(list(range(10, 69))), STATUS_INSUFFICIENT),
        (_history([10] * 60), STATUS_FLAT),
        (_history([1, 2, 3] * 20), STATUS_INSUFFICIENT),
    )

    for history, expected_status in cases:
        result = fit_one_location(history, metric="ship_cnt")
        assert result["status"] == expected_status
        assert result["lower_bound"] is None
        assert result["upper_bound"] is None


def test_duration_fit_rejects_locations_with_too_few_ships():
    result = fit_one_location(
        _history([2] * 60, duration=list(range(10, 70))),
        metric="duration",
    )

    assert result["status"] == STATUS_INSUFFICIENT
    assert result["lower_bound"] is None
    assert result["upper_bound"] is None


def test_duration_fit_excludes_zero_ship_days_and_accepts_reliable_data():
    result = fit_one_location(
        _history(
            [3] * 65 + [0] * 10,
            duration=list(range(10, 75)) + [999] * 10,
        ),
        metric="duration",
        recent_records=60,
    )

    retained = np.arange(15, 75)
    assert result["status"] == STATUS_OK
    assert result["fit_sample_size"] == 60
    assert result["lower_bound"] == np.percentile(retained, 10)
    assert result["upper_bound"] == np.percentile(retained, 90)


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
        recent_records=60,
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
