import sqlite3

import pytest

from mcp_conductor.entry import main_setup_schema as schema


def test_setup_schema_migrates_existing_anomaly_table(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE ship_cnt_in_pipe (
                pipe_name TEXT, date_id INTEGER, ship_cnt INTEGER,
                detection_flag TEXT, PRIMARY KEY (pipe_name, date_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE ship_cnt_in_port (
                port_name TEXT, date_id INTEGER, ship_cnt INTEGER, duration REAL,
                detection_flag TEXT, PRIMARY KEY (port_name, date_id)
            )
            """
        )
        conn.execute(
            "INSERT INTO ship_cnt_in_port (port_name, date_id) VALUES ('legacy_port', 20260701)"
        )
        conn.execute(
            """
            CREATE TABLE m_pipe_anomaly_roll_percentile (
                pipe_name TEXT,
                date_id INTEGER,
                anomaly_flag INTEGER,
                quantile_10 REAL,
                quantile_25 REAL,
                quantile_75 REAL,
                quantile_90 REAL,
                anomaly_ratio REAL,
                updated_timestamp_utc TEXT,
                PRIMARY KEY (pipe_name, date_id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO m_pipe_anomaly_roll_percentile (
                pipe_name, date_id, anomaly_flag, anomaly_ratio
            ) VALUES ('legacy_port', 20260701, 1, 0.5)
            """
        )
        conn.execute(
            """
            CREATE TABLE m_roll_percentile_parameter (
                location_type TEXT,
                location_name TEXT,
                metric TEXT,
                valid_from_date_id INTEGER,
                fit_method TEXT
            )
            """
        )

    monkeypatch.setattr(schema, "DB_PATH", db_path)
    schema.setup_schema()

    with sqlite3.connect(db_path) as conn:
        columns = {
            row[1]: row[2]
            for row in conn.execute("PRAGMA table_info(m_pipe_anomaly_roll_percentile)")
        }
        view_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(vw_m_pipe_anomaly_roll_percentile)")
        }
        parameter_columns = {
            row[1]: row[2]
            for row in conn.execute("PRAGMA table_info(m_roll_percentile_parameter)")
        }
        monitor_columns = {
            row[1]: row[2]
            for row in conn.execute("PRAGMA table_info(m_roll_percentile_monitor)")
        }
        pipe_columns = {
            row[1]: row[2]
            for row in conn.execute("PRAGMA table_info(ship_cnt_in_pipe)")
        }
        primary_key = [
            row[1]
            for row in sorted(
                (
                    row
                    for row in conn.execute(
                        "PRAGMA table_info(m_pipe_anomaly_roll_percentile)"
                    )
                    if row[5]
                ),
                key=lambda row: row[5],
            )
        ]
        migrated = conn.execute(
            """
            SELECT location_type, pipe_name, date_id, anomaly_flag, anomaly_ratio
            FROM m_pipe_anomaly_roll_percentile
            """
        ).fetchone()

    assert columns["location_type"] == "TEXT"
    assert pipe_columns["duration"] == "REAL"
    assert primary_key == ["location_type", "pipe_name", "date_id"]
    assert migrated == ("port", "legacy_port", 20260701, 1, 0.5)
    assert columns["ratio_low"] == "REAL"
    assert columns["ratio_high"] == "REAL"
    assert columns["direction"] == "TEXT"
    assert columns["duration_anomaly_flag"] == "INTEGER"
    assert columns["duration_direction"] == "TEXT"
    assert columns["duration_status"] == "TEXT"
    assert columns["regime"] == "TEXT"
    assert {
        "location_type",
        "ratio_low",
        "ratio_high",
        "direction",
        "duration_anomaly_flag",
        "duration_ratio_low",
        "duration_ratio_high",
        "duration_direction",
        "duration_status",
        "regime",
    } <= view_columns
    assert parameter_columns["training_sample_size"] == "INTEGER"
    assert parameter_columns["calibration_start_date_id"] == "INTEGER"
    assert parameter_columns["calibration_end_date_id"] == "INTEGER"
    assert parameter_columns["calibration_sample_size"] == "INTEGER"
    assert parameter_columns["calibration_target_flag_rate"] == "REAL"
    assert parameter_columns["calibration_flag_rate"] == "REAL"
    assert monitor_columns["snapshot_date_id"] == "INTEGER"
    assert monitor_columns["location_type"] == "TEXT"
    assert monitor_columns["metric"] == "TEXT"
    assert monitor_columns["direction"] == "TEXT"
    assert monitor_columns["flag_rate"] == "REAL"
    assert monitor_columns["status"] == "TEXT"


def test_setup_schema_is_idempotent_with_direction_columns(tmp_path, monkeypatch):
    db_path = tmp_path / "new.sqlite"
    monkeypatch.setattr(schema, "DB_PATH", db_path)

    schema.setup_schema()
    schema.setup_schema()

    with sqlite3.connect(db_path) as conn:
        result_columns = [
            row[1]
            for row in conn.execute("PRAGMA table_info(m_pipe_anomaly_roll_percentile)")
            if row[1]
            in {
                "ratio_low",
                "ratio_high",
                "direction",
                "duration_ratio_low",
                "duration_ratio_high",
                "duration_direction",
                "duration_status",
                "regime",
            }
        ]
        primary_key = [
            row[1]
            for row in sorted(
                (
                    row
                    for row in conn.execute(
                        "PRAGMA table_info(m_pipe_anomaly_roll_percentile)"
                    )
                    if row[5]
                ),
                key=lambda row: row[5],
            )
        ]

    assert primary_key == ["location_type", "pipe_name", "date_id"]
    assert sorted(result_columns) == [
        "direction",
        "duration_direction",
        "duration_ratio_high",
        "duration_ratio_low",
        "duration_status",
        "ratio_high",
        "ratio_low",
        "regime",
    ]


def test_setup_schema_refuses_ambiguous_legacy_result_names(tmp_path, monkeypatch):
    db_path = tmp_path / "ambiguous.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE ship_cnt_in_pipe (pipe_name TEXT, date_id INTEGER)")
        conn.execute("CREATE TABLE ship_cnt_in_port (port_name TEXT, date_id INTEGER)")
        conn.execute(
            """
            CREATE TABLE m_pipe_anomaly_roll_percentile (
                pipe_name TEXT, date_id INTEGER, anomaly_flag INTEGER,
                PRIMARY KEY (pipe_name, date_id)
            )
            """
        )
        conn.execute("INSERT INTO ship_cnt_in_pipe VALUES ('Shared Name', 20260701)")
        conn.execute("INSERT INTO ship_cnt_in_port VALUES ('Shared Name', 20260701)")
        conn.execute(
            "INSERT INTO m_pipe_anomaly_roll_percentile VALUES ('Shared Name', 20260701, 1)"
        )

    monkeypatch.setattr(schema, "DB_PATH", db_path)
    with pytest.raises(ValueError, match="both pipe and port"):
        schema.setup_schema()
