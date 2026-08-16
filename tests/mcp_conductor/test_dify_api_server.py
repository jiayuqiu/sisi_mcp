import asyncio
import unittest
import sqlite3
from unittest.mock import patch, MagicMock

from mcp_conductor.servers.dify_api_server import (
    QuestionRequest,
    analyze_anomaly_reason,
    detect_anomaly,
    parse_question,
)


class TestParseQuestion(unittest.TestCase):
    """Unit tests for the parse_question helper."""

    def test_chinese_date_and_pipe(self):
        run_date, pipe = parse_question("2024年1月马六甲海峡是否拥堵")
        assert run_date == "2024-01-31"
        assert pipe == "马六甲海峡"

    def test_chinese_date_mandeb(self):
        run_date, pipe = parse_question("2023年12月曼德海峡发生异常")
        assert run_date == "2023-12-31"
        assert pipe == "曼德海峡"

    def test_slash_date_format(self):
        run_date, pipe = parse_question("2024/3 马六甲海峡")
        assert run_date == "2024-03-31"
        assert pipe == "马六甲海峡"

    def test_full_date_with_day(self):
        run_date, pipe = parse_question("2024-01-15 曼德海峡是否异常")
        assert run_date == "2024-01-15"
        assert pipe == "曼德海峡"

    def test_empty_question(self):
        run_date, pipe = parse_question("")
        assert run_date is None
        assert pipe is None

    def test_no_date(self):
        run_date, pipe = parse_question("马六甲海峡是否拥堵")
        assert run_date is None
        assert pipe == "马六甲海峡"


class TestDetectAnomaly(unittest.TestCase):
    """Tests for the /api/detect_anomaly endpoint."""

    @staticmethod
    def call_detect(question: str | dict[str, object]) -> dict:
        return asyncio.run(detect_anomaly(QuestionRequest(question=question)))

    def test_unparseable_question(self):
        data = self.call_detect("你好")
        assert data["success"] is False
        assert "无法解析" in data["message"]

    def test_anomaly_detected(self):
        fake_row = (
            1, "红", "异常", 50.0, 80.0, 120.0, 150.0,
            0.25, 0.0, 0.25, "HIGH",
            1, 10.0, 12.0, 18.0, 20.0, 0.4, 0.0, 0.4, "HIGH", "OK",
            "CONGESTION",
        )
        with patch("mcp_conductor.servers.dify_api_server.sqlite3") as mock_sqlite:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = fake_row
            mock_conn.__enter__ = lambda s: mock_conn
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_sqlite.connect.return_value = mock_conn

            data = self.call_detect("2024年1月马六甲海峡是否异常")

        assert data["success"] is True
        assert data["if_anomaly"] is True
        assert data["anomaly_flag"] == 1
        assert data["flag_name"] == "红"
        assert data["pipe_name"] == "马六甲海峡"
        assert data["run_date"] == "2024-01-31"
        assert data["direction"] == "HIGH"
        assert data["ratio_low"] == 0.0
        assert data["ratio_high"] == 0.25
        assert data["duration_direction"] == "HIGH"
        assert data["duration_ratio_high"] == 0.4
        assert data["regime"] == "CONGESTION"
        assert data["route"] == "ANOMALY"
        assert "异常偏高" in data["result"]

    def test_no_anomaly(self):
        fake_row = (
            0, "绿", "正常范围", 50.0, 80.0, 120.0, 150.0,
            0.03, 0.01, 0.02, "NORMAL",
            0, 10.0, 12.0, 18.0, 20.0, 0.03, 0.01, 0.02, "NORMAL", "OK",
            "NORMAL",
        )
        with patch("mcp_conductor.servers.dify_api_server.sqlite3") as mock_sqlite:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = fake_row
            mock_conn.__enter__ = lambda s: mock_conn
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_sqlite.connect.return_value = mock_conn

            data = self.call_detect("2023年12月曼德海峡是否异常")

        assert data["success"] is True
        assert data["if_anomaly"] is False
        assert data["flag_name"] == "绿"
        assert data["direction"] == "NORMAL"
        assert data["duration_direction"] == "NORMAL"
        assert data["regime"] == "NORMAL"
        assert data["route"] == "NORMAL"
        assert "均正常" in data["result"]

    def test_duration_delay_is_anomaly_when_count_is_normal(self):
        fake_row = (
            0, "绿", "正常范围", 50.0, 80.0, 120.0, 150.0,
            0.03, 0.01, 0.02, "NORMAL",
            1, 10.0, 12.0, 18.0, 20.0, 0.5, 0.0, 0.5, "HIGH", "OK",
            "DELAY",
        )
        with patch("mcp_conductor.servers.dify_api_server.sqlite3") as mock_sqlite:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = fake_row
            mock_conn.__enter__ = lambda s: mock_conn
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_sqlite.connect.return_value = mock_conn

            data = self.call_detect(
                {
                    "year": "2026",
                    "month": "07",
                    "day": "21",
                    "location": "英吉利海峡",
                }
            )

        assert data["success"] is True
        assert data["anomaly_flag"] == 0
        assert data["direction"] == "NORMAL"
        assert data["duration_anomaly_flag"] == 1
        assert data["duration_direction"] == "HIGH"
        assert data["regime"] == "DELAY"
        assert data["route"] == "ANOMALY"
        assert data["if_anomaly"] is True
        assert "通行延误" in data["result"]

    def test_port_detection_uses_explicit_location_type(self):
        fake_row = (
            0, "绿", "正常范围", 1.0, 1.0, 4.0, 4.0,
            0.03, 0.01, 0.02, "NORMAL",
            0, 1.0, 1.0, 2.0, 2.0, 0.03, 0.01, 0.02, "NORMAL", "OK",
            "NORMAL",
        )
        with patch("mcp_conductor.servers.dify_api_server.sqlite3") as mock_sqlite:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = fake_row
            mock_conn.__enter__ = lambda s: mock_conn
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_sqlite.connect.return_value = mock_conn

            data = self.call_detect(
                {
                    "year": "2026",
                    "month": "07",
                    "day": "31",
                    "location": "曼萨尼约港",
                    "location_type": "port",
                }
            )

        assert data["success"] is True
        assert data["location_type"] == "port"
        assert mock_conn.execute.call_args.args[1] == ("port", "曼萨尼约港", 20260731)

    def test_no_db_record(self):
        with patch("mcp_conductor.servers.dify_api_server.sqlite3") as mock_sqlite:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = None
            mock_conn.__enter__ = lambda s: mock_conn
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_sqlite.connect.return_value = mock_conn

            data = self.call_detect("2020年1月马六甲海峡是否异常")

        assert data["success"] is False
        assert "未找到" in data["message"]

    def test_anomaly_reason_receives_directional_context(self):
        fake_row = (
            1, 0.7, 0.6, 0.1, "LOW",
            1, 0.5, 0.0, 0.5, "HIGH", "OK", "BLOCKAGE",
        )
        analysis = {
            "summary": "风险摘要。",
            "weather_factor": "天气因素。",
            "political_factor": "政治因素。",
        }
        with (
            patch("mcp_conductor.servers.dify_api_server.sqlite3") as mock_sqlite,
            patch(
                "mcp_conductor.servers.dify_api_server.analyze_congestion",
                return_value=analysis,
            ) as mock_analyze,
        ):
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = fake_row
            mock_conn.__enter__ = lambda s: mock_conn
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_sqlite.connect.return_value = mock_conn

            data = asyncio.run(
                analyze_anomaly_reason(
                    QuestionRequest(
                        question=(
                            '{"year":"2026","month":"04","day":"16",'
                            '"location":"霍尔木兹海峡"}'
                        )
                    )
                )
            )

        assert data["success"] is True
        assert data["direction"] == "LOW"
        assert data["ratio_low"] == 0.6
        assert data["duration_direction"] == "HIGH"
        assert data["regime"] == "BLOCKAGE"
        assert "受阻或封锁" in data["conclusion"]
        mock_analyze.assert_called_once_with(
            "霍尔木兹海峡",
            "2026-04-16",
            location_type="pipe",
            direction="LOW",
            ratio_low=0.6,
            ratio_high=0.1,
            duration_direction="HIGH",
            duration_ratio_low=0.0,
            duration_ratio_high=0.5,
            regime="BLOCKAGE",
        )


def _create_test_db():
    """Create an in-memory SQLite DB with the same schema as sisi.sqlite."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE dim_anomaly_flag (
            flag_value   INTEGER PRIMARY KEY,
            flag_name    TEXT NOT NULL,
            description  TEXT
        )
    """)
    conn.executemany(
        "INSERT INTO dim_anomaly_flag VALUES (?, ?, ?)",
        [
            (0, "NORMAL", "Traffic within historical bounds"),
            (1, "ANOMALY", "Outlier ratio exceeds threshold"),
            (2, "NO_DATA", "Empty DataFrame or all-zero ship_cnt"),
        ],
    )
    conn.execute("""
        CREATE TABLE m_pipe_anomaly_roll_percentile (
            location_type          TEXT NOT NULL,
            pipe_name              TEXT,
            date_id                INTEGER,
            anomaly_flag           INTEGER,
            updated_timestamp_utc  TEXT,
            quantile_10            REAL,
            quantile_25            REAL,
            quantile_75            REAL,
            quantile_90            REAL,
            anomaly_ratio          REAL,
            ratio_low              REAL,
            ratio_high             REAL,
            direction              TEXT,
            duration_anomaly_flag  INTEGER,
            duration_quantile_10   REAL,
            duration_quantile_25   REAL,
            duration_quantile_75   REAL,
            duration_quantile_90   REAL,
            duration_anomaly_ratio REAL,
            duration_ratio_low     REAL,
            duration_ratio_high    REAL,
            duration_direction     TEXT,
            duration_status        TEXT,
            regime                 TEXT,
            PRIMARY KEY (location_type, pipe_name, date_id)
        )
    """)
    conn.execute("""
        CREATE VIEW vw_m_pipe_anomaly_roll_percentile AS
        SELECT
            m.location_type,
            m.pipe_name,
            m.date_id,
            m.anomaly_flag,
            m.quantile_10,
            m.quantile_25,
            m.quantile_75,
            m.quantile_90,
            m.anomaly_ratio,
            m.ratio_low,
            m.ratio_high,
            m.direction,
            m.duration_anomaly_flag,
            m.duration_quantile_10,
            m.duration_quantile_25,
            m.duration_quantile_75,
            m.duration_quantile_90,
            m.duration_anomaly_ratio,
            m.duration_ratio_low,
            m.duration_ratio_high,
            m.duration_direction,
            m.duration_status,
            m.regime,
            d.flag_name,
            d.description,
            m.updated_timestamp_utc
        FROM m_pipe_anomaly_roll_percentile m
        LEFT JOIN dim_anomaly_flag d ON m.anomaly_flag = d.flag_value
    """)
    # seed test rows
    conn.executemany(
        "INSERT INTO m_pipe_anomaly_roll_percentile VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                "pipe", "马六甲海峡", 20240131, 1, "2026-04-05T12:00:00",
                80.0, 100.0, 140.0, 160.0, 0.25, 0.0, 0.25, "HIGH",
                1, 10.0, 12.0, 18.0, 20.0, 0.4, 0.0, 0.4, "HIGH", "OK",
                "CONGESTION",
            ),
            (
                "pipe", "曼德海峡", 20231231, 0, "2026-04-05T12:00:00",
                50.0, 70.0, 130.0, 150.0, 0.03, 0.01, 0.02, "NORMAL",
                0, 10.0, 12.0, 18.0, 20.0, 0.03, 0.01, 0.02, "NORMAL", "OK",
                "NORMAL",
            ),
            (
                "pipe", "马六甲海峡", 20230201, 2, "2026-04-05T12:00:00",
                None, None, None, None, None, None, None, "UNKNOWN",
                2, None, None, None, None, None, None, None, "UNKNOWN", "NO_DATA",
                "UNKNOWN",
            ),
        ],
    )
    conn.commit()
    return conn


class TestDetectAnomalySql(unittest.TestCase):
    """Test the actual SQL query against a real in-memory SQLite DB."""

    QUERY = """
        SELECT
            anomaly_flag,
            flag_name,
            description,
            quantile_10,
            quantile_25,
            quantile_75,
            quantile_90,
            anomaly_ratio,
            ratio_low,
            ratio_high,
            direction,
            duration_anomaly_flag,
            duration_quantile_10,
            duration_quantile_25,
            duration_quantile_75,
            duration_quantile_90,
            duration_anomaly_ratio,
            duration_ratio_low,
            duration_ratio_high,
            duration_direction,
            duration_status,
            regime
        FROM
            vw_m_pipe_anomaly_roll_percentile
        WHERE
            location_type = 'pipe' AND pipe_name = ? AND date_id = ?
    """

    def setUp(self):
        self.conn = _create_test_db()

    def tearDown(self):
        self.conn.close()

    def test_anomaly_row(self):
        row = self.conn.execute(self.QUERY, ("马六甲海峡", 20240131)).fetchone()
        assert row is not None
        (
            anomaly_flag, flag_name, description, q10, q25, q75, q90,
            ratio, ratio_low, ratio_high, direction, duration_flag,
            duration_q10, duration_q25, duration_q75, duration_q90,
            duration_ratio, duration_ratio_low, duration_ratio_high,
            duration_direction, duration_status, regime,
        ) = row
        assert anomaly_flag == 1
        assert flag_name == "ANOMALY"
        assert q10 == 80.0
        assert q25 == 100.0
        assert q75 == 140.0
        assert q90 == 160.0
        assert ratio == 0.25
        assert ratio_low == 0.0
        assert ratio_high == 0.25
        assert direction == "HIGH"
        assert duration_flag == 1
        assert duration_q10 == 10.0
        assert duration_q25 == 12.0
        assert duration_q75 == 18.0
        assert duration_q90 == 20.0
        assert duration_ratio == 0.4
        assert duration_ratio_low == 0.0
        assert duration_ratio_high == 0.4
        assert duration_direction == "HIGH"
        assert duration_status == "OK"
        assert regime == "CONGESTION"

    def test_normal_row(self):
        row = self.conn.execute(self.QUERY, ("曼德海峡", 20231231)).fetchone()
        assert row is not None
        (
            anomaly_flag, flag_name, description, q10, q25, q75, q90,
            ratio, ratio_low, ratio_high, direction, duration_flag,
            duration_q10, duration_q25, duration_q75, duration_q90,
            duration_ratio, duration_ratio_low, duration_ratio_high,
            duration_direction, duration_status, regime,
        ) = row
        assert anomaly_flag == 0
        assert flag_name == "NORMAL"
        assert ratio == 0.03
        assert direction == "NORMAL"
        assert duration_flag == 0
        assert duration_direction == "NORMAL"
        assert duration_status == "OK"
        assert regime == "NORMAL"

    def test_no_data_row(self):
        row = self.conn.execute(self.QUERY, ("马六甲海峡", 20230201)).fetchone()
        assert row is not None
        (
            anomaly_flag, flag_name, description, q10, q25, q75, q90,
            ratio, ratio_low, ratio_high, direction, duration_flag,
            duration_q10, duration_q25, duration_q75, duration_q90,
            duration_ratio, duration_ratio_low, duration_ratio_high,
            duration_direction, duration_status, regime,
        ) = row
        assert anomaly_flag == 2
        assert flag_name == "NO_DATA"
        assert q10 is None
        assert q25 is None
        assert q75 is None
        assert q90 is None
        assert direction == "UNKNOWN"
        assert duration_flag == 2
        assert duration_q10 is None
        assert duration_direction == "UNKNOWN"
        assert duration_status == "NO_DATA"
        assert regime == "UNKNOWN"

    def test_missing_record(self):
        row = self.conn.execute(self.QUERY, ("不存在的海峡", 20240101)).fetchone()
        assert row is None

    def test_view_join_matches_dim(self):
        """Verify the LEFT JOIN produces correct flag_name for all seeded rows."""
        rows = self.conn.execute(
            "SELECT pipe_name, anomaly_flag, flag_name FROM vw_m_pipe_anomaly_roll_percentile ORDER BY date_id"
        ).fetchall()
        expected = [
            ("马六甲海峡", 2, "NO_DATA"),
            ("曼德海峡", 0, "NORMAL"),
            ("马六甲海峡", 1, "ANOMALY"),
        ]
        assert rows == expected
