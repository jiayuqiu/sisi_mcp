import unittest
import sqlite3
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from mcp_conductor.servers.dify_api_server import app, parse_question


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

    def setUp(self):
        self.client = TestClient(app)

    def test_unparseable_question(self):
        resp = self.client.post("/api/detect_anomaly", json={"question": "你好"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "无法解析" in data["message"]

    def test_anomaly_detected(self):
        fake_row = (1, "红", "异常偏高", 50.0, 80.0, 120.0, 150.0, 0.25)
        with patch("mcp_conductor.servers.dify_api_server.sqlite3") as mock_sqlite:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = fake_row
            mock_conn.__enter__ = lambda s: mock_conn
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_sqlite.connect.return_value = mock_conn

            resp = self.client.post(
                "/api/detect_anomaly",
                json={"question": "2024年1月马六甲海峡是否异常"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["if_anomaly"] is True
        assert data["anomaly_flag"] == 1
        assert data["flag_name"] == "红"
        assert data["pipe_name"] == "马六甲海峡"
        assert data["run_date"] == "2024-01-31"
        assert "异常" in data["result"]

    def test_no_anomaly(self):
        fake_row = (0, "绿", "正常范围", 50.0, 80.0, 120.0, 150.0, 0.03)
        with patch("mcp_conductor.servers.dify_api_server.sqlite3") as mock_sqlite:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = fake_row
            mock_conn.__enter__ = lambda s: mock_conn
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_sqlite.connect.return_value = mock_conn

            resp = self.client.post(
                "/api/detect_anomaly",
                json={"question": "2023年12月曼德海峡是否异常"},
            )

        data = resp.json()
        assert data["success"] is True
        assert data["if_anomaly"] is False
        assert data["flag_name"] == "绿"
        assert "无异常" in data["result"]

    def test_no_db_record(self):
        with patch("mcp_conductor.servers.dify_api_server.sqlite3") as mock_sqlite:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = None
            mock_conn.__enter__ = lambda s: mock_conn
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_sqlite.connect.return_value = mock_conn

            resp = self.client.post(
                "/api/detect_anomaly",
                json={"question": "2020年1月马六甲海峡是否异常"},
            )

        data = resp.json()
        assert data["success"] is False
        assert "未找到" in data["message"]


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
            pipe_name              TEXT,
            date_id                INTEGER,
            anomaly_flag           INTEGER,
            updated_timestamp_utc  TEXT,
            quantile_10            REAL,
            quantile_25            REAL,
            quantile_75            REAL,
            quantile_90            REAL,
            anomaly_ratio          REAL,
            PRIMARY KEY (pipe_name, date_id)
        )
    """)
    conn.execute("""
        CREATE VIEW vw_m_pipe_anomaly_roll_percentile AS
        SELECT
            m.pipe_name,
            m.date_id,
            m.anomaly_flag,
            m.quantile_10,
            m.quantile_25,
            m.quantile_75,
            m.quantile_90,
            m.anomaly_ratio,
            d.flag_name,
            d.description,
            m.updated_timestamp_utc
        FROM m_pipe_anomaly_roll_percentile m
        LEFT JOIN dim_anomaly_flag d ON m.anomaly_flag = d.flag_value
    """)
    # seed test rows
    conn.executemany(
        "INSERT INTO m_pipe_anomaly_roll_percentile VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("马六甲海峡", 20240131, 1, "2026-04-05T12:00:00", 80.0, 100.0, 140.0, 160.0, 0.25),
            ("曼德海峡", 20231231, 0, "2026-04-05T12:00:00", 50.0, 70.0, 130.0, 150.0, 0.03),
            ("马六甲海峡", 20230201, 2, "2026-04-05T12:00:00", None, None, None, None, None),
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
            anomaly_ratio
        FROM
            vw_m_pipe_anomaly_roll_percentile
        WHERE
            pipe_name = ? AND date_id = ?
    """

    def setUp(self):
        self.conn = _create_test_db()

    def tearDown(self):
        self.conn.close()

    def test_anomaly_row(self):
        row = self.conn.execute(self.QUERY, ("马六甲海峡", 20240131)).fetchone()
        assert row is not None
        anomaly_flag, flag_name, description, q10, q25, q75, q90, ratio = row
        assert anomaly_flag == 1
        assert flag_name == "ANOMALY"
        assert q10 == 80.0
        assert q25 == 100.0
        assert q75 == 140.0
        assert q90 == 160.0
        assert ratio == 0.25

    def test_normal_row(self):
        row = self.conn.execute(self.QUERY, ("曼德海峡", 20231231)).fetchone()
        assert row is not None
        anomaly_flag, flag_name, description, q10, q25, q75, q90, ratio = row
        assert anomaly_flag == 0
        assert flag_name == "NORMAL"
        assert ratio == 0.03

    def test_no_data_row(self):
        row = self.conn.execute(self.QUERY, ("马六甲海峡", 20230201)).fetchone()
        assert row is not None
        anomaly_flag, flag_name, description, q10, q25, q75, q90, ratio = row
        assert anomaly_flag == 2
        assert flag_name == "NO_DATA"
        assert q10 is None
        assert q25 is None
        assert q75 is None
        assert q90 is None

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
