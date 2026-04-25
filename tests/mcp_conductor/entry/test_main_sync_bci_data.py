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
            detection_flag TEXT,
            PRIMARY KEY (port_name, date_id)
        )
        """
    )
    conn.commit()
    conn.close()


class FakeMetricsAPISuccess:
    def get_metrics_value(self, _start_date, _end_date, zbxxs_val):
        if zbxxs_val == "101-0003,101-0004":
            return {
                "success": True,
                "result": [
                    {
                        "zbrq": "2026-04-20",
                        "xftj1Value": "Test Strait",
                        "zbsj": "10",
                    }
                ],
            }
        if zbxxs_val == "101-0001,101-0002":
            return {
                "success": True,
                "result": [
                    {
                        "zbrq": "2026-04-20",
                        "xftj1Value": "Test Port",
                        "zbsj": "20",
                    }
                ],
            }
        return {"success": False, "result": []}


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

    def test_sync_bci_data_routes_rows_to_pipe_and_port_tables(self):
        with patch.object(sync, "DB_PATH", self.db_path), patch.object(
            sync, "STATUS_PATH", self.status_path
        ), patch.object(sync, "LOG_PATH", self.log_path), patch.object(sync, "MetricsAPI", FakeMetricsAPISuccess):
            result = sync.sync_bci_data("2026-04-20", "2026-04-20")

        assert result == {"success": True, "inserted_count": 2, "reason": None}

        conn = sqlite3.connect(str(self.db_path))
        pipe_row = conn.execute(
            "SELECT pipe_name, date_id, ship_cnt FROM ship_cnt_in_pipe"
        ).fetchone()
        port_row = conn.execute(
            "SELECT port_name, date_id, ship_cnt FROM ship_cnt_in_port"
        ).fetchone()
        conn.close()

        assert pipe_row == ("Test Strait", 20260420, 10)
        assert port_row == ("Test Port", 20260420, 20)

        status = json.loads(self.status_path.read_text(encoding="utf-8"))
        assert status["status"] == "success"
        assert status["inserted_count"] == 2

    def test_sync_bci_data_returns_api_failed_when_all_groups_fail(self):
        with patch.object(sync, "DB_PATH", self.db_path), patch.object(
            sync, "STATUS_PATH", self.status_path
        ), patch.object(sync, "LOG_PATH", self.log_path), patch.object(sync, "MetricsAPI", FakeMetricsAPIFail):
            result = sync.sync_bci_data("2026-04-20", "2026-04-20")

        assert result == {"success": False, "inserted_count": 0, "reason": "api_failed"}

        conn = sqlite3.connect(str(self.db_path))
        pipe_count = conn.execute("SELECT COUNT(*) FROM ship_cnt_in_pipe").fetchone()[0]
        port_count = conn.execute("SELECT COUNT(*) FROM ship_cnt_in_port").fetchone()[0]
        conn.close()

        assert pipe_count == 0
        assert port_count == 0
