"""
Trigger the sisi_expert_chat Dify chatflow for every pipe (pipe_name, date_id) row
in m_pipe_anomaly_roll_percentile within a date range, regardless of
anomaly_flag.

Chatflow routing summary (see mcp_conductor/resources/dify/sisi_expert_chat.yml):

    start -> question-classifier
                class 1 ("是否异常") ─┐
                class 2 ("为什么异常") ─┴─> llm (year/month/day/location extract)
                                              -> detectAnomaly tool
                                              -> Parse & To Json Obj
                                              -> IF/ELSE on combined route
                                                   ANOMALY -> analyzeAnomalyReason (** writes log_agent_worklog **)
                                                   NORMAL -> NORMALSUMMARY       (no log write)
                                                   PARTIAL_DATA/DATA_ISSUE -> DATAISSUESUMMARY (no log write)
                class 3 ("unrelated") -> other-chatbot-stream (no detect/log)

Note: every combined anomaly regime populates log_agent_worklog through the
analyzeAnomalyReason branch, including duration-only anomalies such as DELAY.
Normal and incomplete-data routes exercise summary branches without a log write.

Usage:
    # Dry-run over a date range
    uv run python -m mcp_conductor.entry.main_trigger_dify_chatflow \\
        --start-date 2024-01-01 --end-date 2024-01-31 --dry-run

    # Full run over a date range
    uv run python -m mcp_conductor.entry.main_trigger_dify_chatflow \\
        --start-date 2024-01-01 --end-date 2024-01-31

    # Restrict to a single pipe, cap total calls, slow it down
    uv run python -m mcp_conductor.entry.main_trigger_dify_chatflow \\
        --start-date 2024-01-01 --end-date 2024-01-31 \\
        --pipe 马六甲海峡 --limit 5 --sleep 2

Required environment:
    DIFY_API_KEY       - Dify app API key (for the sisi_expert_chat app)
    DIFY_CHATFLOW_URL  - Base URL, e.g. http://localhost/v1 (no trailing slash)
"""
import argparse
import logging
import os
import sqlite3
import sys
import time
from datetime import date, datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

# Ensure we can import from mcp_conductor if run directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Resolve DB path relative to the repo root (…/sisimcp/data/sisi.sqlite) so the
# script works regardless of the caller's current working directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "sisi.sqlite"


def fetch_detection_targets(
    start_date: date,
    end_date: date,
    pipe_filter: str | None,
) -> list[tuple[str, date]]:
    """
    Return every pipe (pipe_name, date) row from m_pipe_anomaly_roll_percentile
    whose date_id falls in [start_date, end_date], regardless of anomaly_flag.
    Optionally restricted to a single pipe_name.
    """
    start_id = int(start_date.strftime("%Y%m%d"))
    end_id = int(end_date.strftime("%Y%m%d"))

    sql = """
        SELECT pipe_name, date_id
        FROM m_pipe_anomaly_roll_percentile
        WHERE location_type = 'pipe'
          AND date_id BETWEEN ? AND ?
    """
    params: list = [start_id, end_id]
    if pipe_filter:
        sql += " AND pipe_name = ?"
        params.append(pipe_filter)
    sql += " ORDER BY date_id, pipe_name"

    with sqlite3.connect(str(DB_PATH)) as conn:
        rows = conn.execute(sql, params).fetchall()

    results: list[tuple[str, date]] = []
    for pipe_name, date_id in rows:
        s = str(date_id)
        d = date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        results.append((pipe_name, d))
    return results


def build_query(pipe_name: str, run_date: date) -> str:
    """
    Build the natural-language question sent to the Dify chatflow.

    Phrased as a class-2 ("为什么异常") question so the classifier routes into
    the detect -> analyze path. Contains year/month/day/location per the LLM
    extraction schema in sisi_expert_chat.yml.
    """
    return (
        f"请分析{run_date.year}年{run_date.month}月{run_date.day}日"
        f"{pipe_name}为什么会发生交通异常"
    )


def call_dify_chatflow(
    query: str,
    api_key: str,
    base_url: str,
    user: str,
    timeout: float,
) -> dict:
    """
    POST to Dify /chat-messages in blocking mode and return the JSON response.

    The sisi_expert_chat app defines no conversation variables or input
    variables, so `inputs` is empty and each call uses a fresh conversation
    (empty conversation_id) — safe because the detect/analyze path does not
    use the conversation memory window.
    """
    url = f"{base_url.rstrip('/')}/chat-messages"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "inputs": {},
        "query": query,
        "response_mode": "blocking",
        "conversation_id": "",
        "user": user,
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    if not resp.ok:
        # Surface the Dify error body to the caller for easier debugging
        body_preview = (resp.text or "")[:500]
        raise requests.exceptions.HTTPError(
            f"Dify returned {resp.status_code}: {body_preview}",
            response=resp,
        )
    return resp.json()


def parse_iso_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def is_retryable_dify_error(error: requests.exceptions.RequestException) -> bool:
    """Return whether a failed chatflow call is safe to retry."""
    if isinstance(error, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
        return True

    response = getattr(error, "response", None)
    if response is None:
        return False
    if response.status_code == 429 or response.status_code >= 500:
        return True
    return response.status_code == 400 and "timed out" in (response.text or "").lower()


def run(
    start_date: date,
    end_date: date,
    pipe_filter: str | None,
    dry_run: bool,
    limit: int | None,
    sleep: float,
    user: str,
    timeout: float,
    retries: int = 2,
    retry_backoff: float = 2.0,
) -> None:
    if start_date > end_date:
        logger.error("start-date (%s) must be <= end-date (%s).", start_date, end_date)
        return
    if not DB_PATH.exists():
        logger.error("Database not found at %s", DB_PATH.absolute())
        return

    logger.info("Date range: %s to %s (inclusive)", start_date, end_date)
    if pipe_filter:
        logger.info("Pipe filter: %s", pipe_filter)

    targets = fetch_detection_targets(start_date, end_date, pipe_filter)
    logger.info(
        "Found %d row(s) in m_pipe_anomaly_roll_percentile for this range.",
        len(targets),
    )

    if limit is not None:
        targets = targets[:limit]

    total = len(targets)
    logger.info("Total targets: %d", total)

    if total == 0:
        logger.info("Nothing to do. Exiting.")
        return

    if dry_run:
        logger.info("Dry run — previewing queries without calling Dify:")
        for pipe, d in targets:
            logger.info("  [%s] %s -> %s", pipe, d.isoformat(), build_query(pipe, d))
        return

    # Validate env vars only when actually calling Dify
    api_key = os.getenv("DIFY_API_KEY", "")
    base_url = os.getenv("DIFY_CHATFLOW_URL", "")
    if not api_key:
        logger.error("DIFY_API_KEY is not set. Aborting.")
        return
    if not base_url:
        logger.error("DIFY_CHATFLOW_URL is not set. Aborting.")
        return

    logger.info("Dify base URL: %s", base_url)

    succeeded, failed = 0, 0
    for i, (pipe, d) in enumerate(targets, start=1):
        query = build_query(pipe, d)
        logger.info("[%d/%d] %s %s -> %s", i, total, pipe, d.isoformat(), query)
        try:
            resp = None
            for attempt in range(retries + 1):
                try:
                    resp = call_dify_chatflow(
                        query=query,
                        api_key=api_key,
                        base_url=base_url,
                        user=user,
                        timeout=timeout,
                    )
                    break
                except requests.exceptions.RequestException as error:
                    if attempt >= retries or not is_retryable_dify_error(error):
                        raise
                    delay = retry_backoff * (2**attempt)
                    logger.warning(
                        "[%d/%d] RETRY %d/%d %s %s after %.1fs: %s",
                        i,
                        total,
                        attempt + 1,
                        retries,
                        pipe,
                        d.isoformat(),
                        delay,
                        error,
                    )
                    if delay > 0:
                        time.sleep(delay)

            if resp is None:
                raise RuntimeError("Dify call finished without a response")
            answer = resp.get("answer") or ""
            message_id = resp.get("message_id", "")
            date_id = int(d.strftime("%Y%m%d"))
            return_id = f"dify-{message_id}" if message_id else f"dify-{pipe}-{date_id}"
            answer_preview = answer[:120].replace("\n", " ")
            logger.info(
                "[%d/%d] OK message_id=%s answer=%s...",
                i, total, message_id, answer_preview,
            )
            # Upsert final answer into log_agent_worklog so content is always the latest.
            if answer:
                with sqlite3.connect(str(DB_PATH)) as conn:
                    conn.execute(
                        """INSERT INTO log_agent_worklog
                               (return_id, question_type, full_response, payload, date_id, pipe_name, content, reasoning_content)
                           VALUES (?, ?, '', ?, ?, ?, ?, '')
                           ON CONFLICT(pipe_name, date_id) DO UPDATE SET
                               content = excluded.content,
                               return_id = excluded.return_id,
                               run_timestamp = datetime('now'),
                               payload = CASE
                                   WHEN log_agent_worklog.payload IS NULL OR log_agent_worklog.payload = ''
                                       THEN excluded.payload
                                   ELSE log_agent_worklog.payload
                               END,
                               question_type = CASE
                                   WHEN log_agent_worklog.question_type IS NULL OR log_agent_worklog.question_type = ''
                                       THEN excluded.question_type
                                   ELSE log_agent_worklog.question_type
                               END,
                               pipe_name = COALESCE(log_agent_worklog.pipe_name, excluded.pipe_name),
                               date_id = COALESCE(log_agent_worklog.date_id, excluded.date_id)""",
                        (return_id, "dify_answer", query, date_id, pipe, answer),
                    )
                    updated = conn.execute(
                        "SELECT changes()"
                    ).fetchone()[0]
                if updated:
                    logger.info(
                        "[%d/%d] Upserted content to DB for pipe=%s date_id=%s return_id=%s",
                        i,
                        total,
                        pipe,
                        date_id,
                        return_id,
                    )
                else:
                    logger.debug("[%d/%d] No DB row changed for pipe=%s date_id=%s", i, total, pipe, date_id)
            succeeded += 1
        except requests.exceptions.RequestException as e:
            failed += 1
            logger.error("[%d/%d] FAILED %s %s: %s", i, total, pipe, d.isoformat(), e)
        except Exception as e:
            failed += 1
            logger.error("[%d/%d] UNEXPECTED ERROR %s %s: %s", i, total, pipe, d.isoformat(), e)

        if sleep > 0 and i < total:
            time.sleep(sleep)

    logger.info("Done. Succeeded=%d, Failed=%d, Total=%d", succeeded, failed, total)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Trigger the Dify chatflow for each pipe over a date range.",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        required=True,
        help="Start date (inclusive), format YYYY-MM-DD.",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        required=True,
        help="End date (inclusive), format YYYY-MM-DD.",
    )
    parser.add_argument(
        "--pipe",
        type=str,
        default=None,
        help="Only trigger for this pipe_name (default: all pipes found in "
             "m_pipe_anomaly_roll_percentile for the date range).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the queries that would be sent without calling Dify.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap the total number of calls (useful for testing).",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=1.0,
        help="Seconds to sleep between Dify calls (default: 1.0).",
    )
    parser.add_argument(
        "--user",
        type=str,
        default="backfill-script",
        help="'user' field sent to Dify (default: backfill-script).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="Per-request HTTP timeout in seconds (default: 180).",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Retries for timeouts, connection errors, HTTP 429, and HTTP 5xx (default: 2).",
    )
    parser.add_argument(
        "--retry-backoff",
        type=float,
        default=2.0,
        help="Initial retry delay in seconds; doubles after each retry (default: 2).",
    )
    args = parser.parse_args()

    if args.retries < 0:
        parser.error("--retries must be zero or greater")
    if args.retry_backoff < 0:
        parser.error("--retry-backoff must be zero or greater")

    run(
        start_date=parse_iso_date(args.start_date),
        end_date=parse_iso_date(args.end_date),
        pipe_filter=args.pipe,
        dry_run=args.dry_run,
        limit=args.limit,
        sleep=args.sleep,
        user=args.user,
        timeout=args.timeout,
        retries=args.retries,
        retry_backoff=args.retry_backoff,
    )


if __name__ == "__main__":
    main()
