import os
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from mcp_conductor.entry import main_trigger_dify_chatflow as trigger


def _init_test_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE m_pipe_anomaly_roll_percentile (
            pipe_name TEXT,
            date_id INTEGER,
            anomaly_flag INTEGER,
            PRIMARY KEY (pipe_name, date_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE log_agent_worklog (
            return_id TEXT UNIQUE NOT NULL,
            question_type TEXT,
            full_response TEXT,
            payload TEXT,
            date_id INT,
            pipe_name TEXT,
            run_timestamp TEXT DEFAULT (datetime('now')),
            content TEXT,
            reasoning_content TEXT,
            PRIMARY KEY (pipe_name, date_id)
        )
        """
    )
    conn.execute(
        "INSERT INTO m_pipe_anomaly_roll_percentile (pipe_name, date_id, anomaly_flag) VALUES (?, ?, ?)",
        ("霍尔木兹海峡", 20260415, 1),
    )
    conn.commit()
    conn.close()


class TestTriggerChatflowWorklogUpsert(unittest.TestCase):
    LIVE_DIFY_API_KEY_ENV = "TEST_DIFY_CHATFLOW_API_KEY"
    LIVE_DIFY_BASE_URL_ENV = "TEST_DIFY_CHATFLOW_URL"

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.sqlite"
        _init_test_db(self.db_path)

    def tearDown(self):
        self.tmpdir.cleanup()

    @patch.object(trigger, "call_dify_chatflow")
    def test_insert_new_worklog_row(self, mock_call):
        mock_call.return_value = {
            "answer": "new final answer",
            "message_id": "msg-insert-1",
        }

        with patch.object(trigger, "DB_PATH", self.db_path), patch.dict(
            os.environ,
            {"DIFY_API_KEY": "dummy", "DIFY_CHATFLOW_URL": "http://example/v1"},
            clear=False,
        ):
            trigger.run(
                start_date=date(2026, 4, 15),
                end_date=date(2026, 4, 15),
                pipe_filter="霍尔木兹海峡",
                dry_run=False,
                limit=None,
                sleep=0,
                user="test-user",
                timeout=5.0,
            )

        conn = sqlite3.connect(str(self.db_path))
        row = conn.execute(
            """
            SELECT return_id, question_type, date_id, pipe_name, content
            FROM log_agent_worklog
            WHERE pipe_name = ? AND date_id = ?
            """,
            ("霍尔木兹海峡", 20260415),
        ).fetchone()
        conn.close()

        assert row is not None
        return_id, question_type, date_id, pipe_name, content = row
        assert return_id == "dify-msg-insert-1"
        assert question_type == "dify_answer"
        assert date_id == 20260415
        assert pipe_name == "霍尔木兹海峡"
        assert content == "new final answer"

    @patch.object(trigger, "call_dify_chatflow")
    def test_update_existing_worklog_row_by_pipe_and_date(self, mock_call):
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            """
            INSERT INTO log_agent_worklog
            (return_id, question_type, full_response, payload, date_id, pipe_name, content, reasoning_content)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "old-return-id",
                "weather_news",
                "",
                "existing-payload",
                20260415,
                "霍尔木兹海峡",
                "old short content",
                "",
            ),
        )
        conn.commit()
        conn.close()

        mock_call.return_value = {
            "answer": "new long final answer",
            "message_id": "msg-update-2",
        }

        with patch.object(trigger, "DB_PATH", self.db_path), patch.dict(
            os.environ,
            {"DIFY_API_KEY": "dummy", "DIFY_CHATFLOW_URL": "http://example/v1"},
            clear=False,
        ):
            trigger.run(
                start_date=date(2026, 4, 15),
                end_date=date(2026, 4, 15),
                pipe_filter="霍尔木兹海峡",
                dry_run=False,
                limit=None,
                sleep=0,
                user="test-user",
                timeout=5.0,
            )

        conn = sqlite3.connect(str(self.db_path))
        row = conn.execute(
            """
            SELECT return_id, question_type, payload, content
            FROM log_agent_worklog
            WHERE pipe_name = ? AND date_id = ?
            """,
            ("霍尔木兹海峡", 20260415),
        ).fetchone()
        conn.close()

        assert row is not None
        return_id, question_type, payload, content = row
        assert return_id == "dify-msg-update-2"
        # Preserve existing non-empty metadata on update.
        assert question_type == "weather_news"
        assert payload == "existing-payload"
        assert content == "new long final answer"

    @unittest.skip("skip. only trigger in developing.")
    def test_call_dify_chatflow(self):
        result = trigger.call_dify_chatflow(
            query="请分析2026年4月15日霍尔木兹海峡为什么会发生交通异常",
            api_key=os.environ[self.LIVE_DIFY_API_KEY_ENV],
            base_url=os.environ[self.LIVE_DIFY_BASE_URL_ENV],
            user="test-user",
            timeout=30.0,
        )

        assert isinstance(result, dict)
        assert result.get("message_id")
        assert isinstance(result.get("answer"), str)
