import sqlite3

from mcp_conductor.detector.plot_ship_congestion import plot_ship_congestion
from mcp_conductor.entry.main_setup_schema import SQL_CREATE_M_PIPE_ANOMALY_ROLL_PERCENTILE


def test_plot_ship_congestion_renders_count_duration_and_regimes(tmp_path):
    db_path = tmp_path / "plot.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE ship_cnt_in_pipe (
                pipe_name TEXT,
                date_id INTEGER,
                ship_cnt INTEGER,
                duration REAL
            )
            """
        )
        conn.execute(SQL_CREATE_M_PIPE_ANOMALY_ROLL_PERCENTILE)
        conn.executemany(
            "INSERT INTO ship_cnt_in_pipe VALUES (?, ?, ?, ?)",
            [
                ("test_pipe", 20260601, 20, 12.0),
                ("test_pipe", 20260602, 30, 20.0),
                ("test_pipe", 20260603, 35, 24.0),
            ],
        )
        conn.execute(
            """
            INSERT INTO m_pipe_anomaly_roll_percentile (
                location_type, pipe_name, date_id, anomaly_flag, direction,
                duration_anomaly_flag, duration_direction, duration_status, regime
            ) VALUES ('pipe', 'test_pipe', 20260603, 1, 'HIGH', 1, 'HIGH', 'OK', 'CONGESTION')
            """
        )

    image_path = plot_ship_congestion(
        "2026-06-03",
        "test_pipe",
        month=0,
        day=3,
        output_dir=tmp_path / "images",
        db_path=db_path,
    )

    rendered = (tmp_path / "images" / "ship_congestion_test_pipe_20260603.png")
    assert image_path == str(rendered)
    assert rendered.read_bytes().startswith(b"\x89PNG")
