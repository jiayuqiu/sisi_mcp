import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp_conductor.entry import main_sync_bci_data as sync


def _init_test_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
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
    conn.execute(
        """
        CREATE TABLE ship_cnt_in_port (
            port_name TEXT,
            date_id INTEGER,
            ship_cnt INTEGER,
            duration REAL,
            detection_flag TEXT,
            PRIMARY KEY (port_name, date_id)
        )
        """
    )
    conn.commit()
    conn.close()


def _fake_api(strait_rows, port_rows):
    """Build a fake MetricsAPI class returning the given rows per zbxxs group."""

    class FakeMetricsAPI:
        def get_metrics_value(self, _start_date, _end_date, zbxxs_val):
            if zbxxs_val == "101-0003,101-0004":
                return {"success": True, "result": strait_rows}
            if zbxxs_val == "101-0001,101-0002":
                return {"success": True, "result": port_rows}
            return {"success": False, "result": []}

    return FakeMetricsAPI


def _row(location, zbxx, zbsj, date="2026-04-20"):
    return {"zbrq": date, "xftj1Value": location, "zbxx": zbxx, "zbsj": zbsj}


# Both metrics per group, as the real API returns them.
FakeMetricsAPISuccess = _fake_api(
    strait_rows=[
        _row("Test Strait", "101-0003", "10"),
        _row("Test Strait", "101-0004", "292.143977492679"),
    ],
    port_rows=[
        _row("Test Port", "101-0001", "20"),
        _row("Test Port", "101-0002", "48.5"),
    ],
)


class FakeMetricsAPIFail:
    def get_metrics_value(self, _start_date, _end_date, zbxxs_val=None):
        return {"success": False, "result": []}


class TestSyncBCIData(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tmpdir.name)
        self.db_path = self.base / "sisi_tmp.sqlite"
        self.status_path = self.base / "sync_status.json"
        self.log_path = self.base / "sync_history.jsonl"
        _init_test_db(self.db_path)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _run_sync(self, api, start="2026-04-20", end="2026-04-20"):
        with patch.object(sync, "DB_PATH", self.db_path), patch.object(
            sync, "STATUS_PATH", self.status_path
        ), patch.object(sync, "LOG_PATH", self.log_path), patch.object(sync, "MetricsAPI", api):
            return sync.sync_bci_data(start, end)

    def _query(self, sql):
        conn = sqlite3.connect(str(self.db_path))
        try:
            return conn.execute(sql).fetchall()
        finally:
            conn.close()

    def test_sync_bci_data_routes_rows_to_pipe_and_port_tables(self):
        result = self._run_sync(FakeMetricsAPISuccess)

        assert result == {"success": True, "inserted_count": 4, "reason": None}

        assert self._query("SELECT pipe_name, date_id, ship_cnt FROM ship_cnt_in_pipe") == [
            ("Test Strait", 20260420, 10)
        ]
        assert self._query("SELECT port_name, date_id, ship_cnt FROM ship_cnt_in_port") == [
            ("Test Port", 20260420, 20)
        ]

        status = json.loads(self.status_path.read_text(encoding="utf-8"))
        assert status["status"] == "success"
        assert status["inserted_count"] == 4

    def test_sync_bci_data_stores_count_and_duration_in_same_row(self):
        """Regression: count and duration arrive as separate zbxx items keyed on the
        same (location, date_id). An INSERT OR REPLACE write nulls whichever landed
        first, so both columns must survive in a single row."""
        self._run_sync(FakeMetricsAPISuccess)

        assert self._query("SELECT ship_cnt, duration FROM ship_cnt_in_pipe") == [
            (10, 292.143977492679)
        ]
        assert self._query("SELECT ship_cnt, duration FROM ship_cnt_in_port") == [(20, 48.5)]

    def test_sync_bci_data_preserves_sibling_column_and_flag_on_resync(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            "INSERT INTO ship_cnt_in_pipe VALUES ('Test Strait', 20260420, NULL, NULL, '红')"
        )
        conn.commit()
        conn.close()

        self._run_sync(FakeMetricsAPISuccess)
        self._run_sync(FakeMetricsAPISuccess)

        assert self._query(
            "SELECT ship_cnt, duration, detection_flag FROM ship_cnt_in_pipe"
        ) == [(10, 292.143977492679, "红")]

    def test_sync_bci_data_skips_unroutable_zbxx_without_failing_the_day(self):
        api = _fake_api(
            strait_rows=[
                _row("Test Strait", None, "99"),
                _row("Test Strait", "101-9999", "99"),
                _row("Test Strait", "101-0003", "10"),
            ],
            port_rows=[_row("Test Port", "101-0001", "20")],
        )

        result = self._run_sync(api)

        assert result == {"success": True, "inserted_count": 2, "reason": None}
        # The unroutable rows must not leak their value into the count column.
        assert self._query("SELECT ship_cnt FROM ship_cnt_in_pipe") == [(10,)]

    def test_sync_bci_data_accepts_counts_formatted_as_decimals(self):
        """zbsj is a string; a count of "10.0" must parse rather than be dropped."""
        api = _fake_api(
            strait_rows=[_row("Test Strait", "101-0003", "10.0")],
            port_rows=[_row("Test Port", "101-0001", "20.0")],
        )

        result = self._run_sync(api)

        assert result["inserted_count"] == 2
        assert self._query("SELECT ship_cnt FROM ship_cnt_in_pipe") == [(10,)]
        assert self._query("SELECT ship_cnt FROM ship_cnt_in_port") == [(20,)]

    def test_sync_rejects_canals_as_ports_but_keeps_their_pipe_metrics(self):
        api = _fake_api(
            strait_rows=[
                _row("巴拿马运河", "101-0003", "10"),
                _row("巴拿马运河", "101-0004", "30.5"),
                _row("苏伊士运河", "101-0003", "8"),
                _row("苏伊士运河", "101-0004", "42.0"),
            ],
            port_rows=[
                _row("巴拿马运河", "101-0001", "10"),
                _row("巴拿马运河", "101-0002", "30.5"),
                _row("苏伊士运河", "101-0001", "8"),
                _row("苏伊士运河", "101-0002", "42.0"),
                _row("Test Port", "101-0001", "20"),
                _row("Test Port", "101-0002", "48.5"),
            ],
        )

        result = self._run_sync(api)

        assert result == {"success": True, "inserted_count": 6, "reason": None}
        assert self._query(
            "SELECT pipe_name, ship_cnt, duration FROM ship_cnt_in_pipe ORDER BY pipe_name"
        ) == [
            ("巴拿马运河", 10, 30.5),
            ("苏伊士运河", 8, 42.0),
        ]
        assert self._query(
            "SELECT port_name, ship_cnt, duration FROM ship_cnt_in_port"
        ) == [("Test Port", 20, 48.5)]

    def test_sync_bci_data_returns_api_failed_when_all_groups_fail(self):
        result = self._run_sync(FakeMetricsAPIFail)

        assert result == {"success": False, "inserted_count": 0, "reason": "api_failed"}

        assert self._query("SELECT COUNT(*) FROM ship_cnt_in_pipe") == [(0,)]
        assert self._query("SELECT COUNT(*) FROM ship_cnt_in_port") == [(0,)]
