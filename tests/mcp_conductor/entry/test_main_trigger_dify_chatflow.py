import os
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import requests

from mcp_conductor.entry import main_trigger_dify_chatflow as trigger


def _init_test_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE m_pipe_anomaly_roll_percentile (
            location_type TEXT NOT NULL,
            pipe_name TEXT,
            date_id INTEGER,
            anomaly_flag INTEGER,
            PRIMARY KEY (location_type, pipe_name, date_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE log_agent_worklog (
            location_type TEXT NOT NULL,
            return_id TEXT UNIQUE NOT NULL,
            question_type TEXT,
            full_response TEXT,
            payload TEXT,
            date_id INT,
            pipe_name TEXT,
            run_timestamp TEXT DEFAULT (datetime('now')),
            content TEXT,
            reasoning_content TEXT,
            PRIMARY KEY (location_type, pipe_name, date_id)
        )
        """
    )
    conn.execute(
        "INSERT INTO m_pipe_anomaly_roll_percentile (location_type, pipe_name, date_id, anomaly_flag) VALUES (?, ?, ?, ?)",
        ("pipe", "霍尔木兹海峡", 20260415, 1),
    )
    conn.execute(
        "INSERT INTO m_pipe_anomaly_roll_percentile (location_type, pipe_name, date_id, anomaly_flag) VALUES (?, ?, ?, ?)",
        ("port", "霍尔木兹海峡", 20260415, 1),
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
                location_type_filter="pipe",
            )

        conn = sqlite3.connect(str(self.db_path))
        row = conn.execute(
            """
            SELECT return_id, question_type, date_id, pipe_name, content
            FROM log_agent_worklog
            WHERE location_type = 'pipe' AND pipe_name = ? AND date_id = ?
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
        mock_call.assert_called_once()

    @patch.object(trigger, "call_dify_chatflow")
    def test_update_existing_worklog_row_by_pipe_and_date(self, mock_call):
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            """
            INSERT INTO log_agent_worklog
            (location_type, return_id, question_type, full_response, payload, date_id, pipe_name, content, reasoning_content)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "pipe",
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
                location_type_filter="pipe",
            )

        conn = sqlite3.connect(str(self.db_path))
        row = conn.execute(
            """
            SELECT return_id, question_type, payload, content
            FROM log_agent_worklog
            WHERE location_type = 'pipe' AND pipe_name = ? AND date_id = ?
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

    @patch.object(trigger, "call_dify_chatflow")
    def test_retries_dify_internal_timeout_then_succeeds(self, mock_call):
        timeout_response = requests.Response()
        timeout_response.status_code = 400
        timeout_response._content = b'{"message":"Run failed: timed out"}'
        timeout_error = requests.exceptions.HTTPError(
            "Dify returned 400: timed out",
            response=timeout_response,
        )
        mock_call.side_effect = [
            timeout_error,
            {"answer": "answer after retry", "message_id": "msg-retry-1"},
        ]

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
                retries=1,
                retry_backoff=0,
                location_type_filter="pipe",
            )

        assert mock_call.call_count == 2
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT content FROM log_agent_worklog WHERE location_type = 'pipe' AND pipe_name = ? AND date_id = ?",
                ("霍尔木兹海峡", 20260415),
            ).fetchone()
        assert row == ("answer after retry",)

    @patch.object(trigger, "call_dify_chatflow")
    def test_non_retryable_dify_error_logs_diagnostics(self, mock_call):
        response = requests.Response()
        response.status_code = 400
        response.reason = "Bad Request"
        response.url = "http://example/v1/chat-messages"
        response.headers["content-type"] = "application/json"
        response.headers["x-request-id"] = "dify-request-123"
        response._content = (
            b'{"message":"Run failed: could not find json block in the output.",'
            + (b'"detail":"' + b"x" * 600 + b'FULL-BODY-MARKER"}')
        )
        mock_call.side_effect = requests.exceptions.HTTPError(
            "Dify returned 400",
            response=response,
        )

        with patch.object(trigger, "DB_PATH", self.db_path), patch.dict(
            os.environ,
            {"DIFY_API_KEY": "dummy", "DIFY_CHATFLOW_URL": "http://example/v1"},
            clear=False,
        ), self.assertLogs(trigger.logger, level="ERROR") as captured:
            trigger.run(
                start_date=date(2026, 4, 15),
                end_date=date(2026, 4, 15),
                pipe_filter="霍尔木兹海峡",
                dry_run=False,
                limit=None,
                sleep=0,
                user="test-user",
                timeout=5.0,
                retries=2,
                retry_backoff=0,
                location_type_filter="pipe",
            )

        log_output = "\n".join(captured.output)
        assert "after 1 attempt(s)" in log_output
        assert "retryable=False" in log_output
        assert "status=400" in log_output
        assert "x-request-id=dify-request-123" in log_output
        assert "FULL-BODY-MARKER" in log_output
        assert "请分析2026年4月15日" in log_output
        assert mock_call.call_count == 1

    @patch.object(trigger, "call_dify_chatflow")
    def test_all_location_types_are_logged_separately(self, mock_call):
        mock_call.side_effect = [
            {"answer": "pipe answer", "message_id": "pipe-message"},
            {"answer": "port answer", "message_id": "port-message"},
        ]

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
                location_type_filter="all",
            )

        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT location_type, content FROM log_agent_worklog ORDER BY location_type"
            ).fetchall()
        assert rows == [("pipe", "pipe answer"), ("port", "port answer")]

    def test_missing_only_excludes_existing_typed_log(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """
                INSERT INTO log_agent_worklog
                    (location_type, return_id, date_id, pipe_name, content)
                VALUES ('pipe', 'existing-pipe', 20260415, '霍尔木兹海峡', 'done')
                """
            )

        with patch.object(trigger, "DB_PATH", self.db_path):
            targets = trigger.fetch_detection_targets(
                date(2026, 4, 15),
                date(2026, 4, 15),
                "霍尔木兹海峡",
                location_type_filter="all",
                missing_only=True,
            )

        assert targets == [("port", "霍尔木兹海峡", date(2026, 4, 15))]

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
