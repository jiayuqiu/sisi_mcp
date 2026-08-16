import json
import uuid
from pathlib import Path

from sqlalchemy import Engine, create_engine
import sqlite3

from .logger import get_logger

logger = get_logger(__name__)

DB_PATH = Path("./data/sisi.sqlite")

_engine: Engine | None = None


def get_engine() -> Engine:
    """Return a cached SQLAlchemy engine for sisi.sqlite."""
    global _engine
    if _engine is None:
        _engine = create_engine(f"sqlite:///{DB_PATH.absolute()}")
    return _engine


def save_to_log(
    response: dict,
    payload: str,
    date_id: int,
    pipe_name: str,
    question_type: str = "weather_news",
    location_type: str = "pipe",
) -> None:
    """Persist a DeepSeek API response to log_agent_worklog."""
    try:
        return_id = response.get("id", "")
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        reasoning_content = response.get("choices", [{}])[0].get("message", {}).get("reasoning_content", "")
        full_response = json.dumps(response, ensure_ascii=False)

        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            """INSERT OR REPLACE INTO log_agent_worklog
               (location_type, return_id, question_type, full_response, payload,
                date_id, pipe_name, content, reasoning_content)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                location_type,
                return_id,
                question_type,
                full_response,
                payload,
                date_id,
                pipe_name,
                content,
                reasoning_content,
            ),
        )
        conn.commit()
        conn.close()
        logger.info("Saved log for return_id=%s, pipe_name=%s, date_id=%s", return_id, pipe_name, date_id)
    except Exception as e:
        logger.error("Failed to save log: %s", e)


def save_worklog_entry(
    content: str,
    pipe_name: str,
    date_id: int,
    question_type: str,
    payload: str = "",
    reasoning_content: str = "",
    return_id: str | None = None,
    location_type: str = "pipe",
) -> str:
    """Persist a summary entry (e.g. from a Dify LLM node) to log_agent_worklog.

    Unlike `save_to_log`, this accepts a plain content string rather than a
    full DeepSeek response payload. Generates a UUID-based return_id when
    none is supplied, since Dify LLM nodes do not surface the upstream id.

    Returns the return_id used for the inserted row.
    """
    if not return_id:
        return_id = f"dify-{uuid.uuid4().hex}"
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            """INSERT OR REPLACE INTO log_agent_worklog
               (location_type, return_id, question_type, full_response, payload,
                date_id, pipe_name, content, reasoning_content)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                location_type,
                return_id,
                question_type,
                "",
                payload,
                date_id,
                pipe_name,
                content,
                reasoning_content,
            ),
        )
        conn.commit()
        conn.close()
        logger.info(
            "Saved worklog entry return_id=%s type=%s pipe_name=%s date_id=%s",
            return_id, question_type, pipe_name, date_id,
        )
        return return_id
    except Exception as e:
        logger.error("Failed to save worklog entry: %s", e)
        raise
