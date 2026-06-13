"""Dummy MCP Server — self-contained starter template.

Local tools:   echo, current time, DB query, doc read
External tool: invoke a remote MCP server
"""

import argparse
import json
import logging
import os
import sqlite3
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from fastmcp import FastMCP

logger = logging.getLogger("dummy_mcp")

mcp = FastMCP("dummy-server")


# ── Helpers ────────────────────────────────────────────────────────────

def _default_db_path() -> str:
    return os.environ.get("DUMMY_DB_PATH", str(Path(__file__).resolve().parent.parent.parent.parent / "data" / "sisi.sqlite"))


def _default_docs_dir() -> str:
    return os.environ.get("DUMMY_DOCS_DIR", os.getcwd())


# ── Local Tools ────────────────────────────────────────────────────────

@mcp.tool()
async def echo(message: str) -> str:
    """Echo the input message back. Useful for connectivity checks."""
    if not message:
        return "Error: message is required."
    return f"Echo: {message}"


@mcp.tool()
async def get_current_time() -> str:
    """Return the current server time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


@mcp.tool()
async def query_local_db(sql: str) -> str:
    """Run a read-only SQL query against the local SQLite database.

    Returns results as a JSON string. Use this to inspect
    ship counts, work history, or any table in the local DB.
    """
    sql_stripped = sql.strip()
    if not sql_stripped:
        return json.dumps({"error": "sql query is empty"})
    if not sql_stripped.upper().startswith("SELECT"):
        return json.dumps({"error": "only SELECT queries are allowed"})

    db_path = _default_db_path()
    if not os.path.exists(db_path):
        return json.dumps({"error": f"database not found at {db_path}"})

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cur = conn.execute(sql_stripped)
        rows = [dict(row) for row in cur.fetchall()]
        conn.close()
        return json.dumps(rows, ensure_ascii=False, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def read_local_doc(relative_path: str) -> str:
    """Read the contents of a local file under the docs directory.

    Only files whose names end with .md, .txt, or .json are allowed.
    """
    if not relative_path:
        return json.dumps({"error": "path is required"})

    allowed = {".md", ".txt", ".json"}
    ext = Path(relative_path).suffix.lower()
    if ext not in allowed:
        return json.dumps({"error": f"file extension '{ext}' not allowed. Allowed: {sorted(allowed)}"})

    docs_dir = Path(_default_docs_dir())
    full_path = (docs_dir / relative_path).resolve()
    if not str(full_path).startswith(str(docs_dir.resolve())):
        return json.dumps({"error": "path traversal is not allowed"})

    try:
        return full_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return json.dumps({"error": f"file not found: {relative_path}"})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ── External MCP Tool ──────────────────────────────────────────────────

@mcp.tool()
async def invoke_external_mcp(server_url: str, tool_name: str,
                               arguments: str = "{}") -> str:
    """Invoke a tool on an external MCP server.

    Uses the MCP streamable-http protocol to connect, list tools,
    call the requested tool, and return the result.
    """
    tools = await _list_external_tools(server_url)
    result = await _call_external_tool(server_url, tool_name, arguments)
    return json.dumps({"server": server_url, "tools_available": tools, "result": result}, ensure_ascii=False)


async def _list_external_tools(server_url: str) -> list:
    """List tools exposed by a remote MCP server."""
    url = server_url.rstrip("/") + "/tools/list"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return [{"error": str(exc)}]


async def _call_external_tool(server_url: str, tool_name: str,
                               arguments: str) -> str:
    """Call a specific tool on a remote MCP server."""
    url = server_url.rstrip("/") + "/tools/call"
    try:
        payload = json.dumps({
            "name": tool_name,
            "arguments": json.loads(arguments) if arguments else {},
        }).encode("utf-8")
    except json.JSONDecodeError:
        return json.dumps({"error": f"invalid JSON arguments: {arguments}"})

    try:
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return json.dumps({"error": f"HTTP {exc.code} {exc.reason}", "detail": body})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ── Entrypoint ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dummy MCP Server")
    parser.add_argument("--host", default=os.environ.get("MCP_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MCP_PORT", "8001")))
    parser.add_argument("--transport", default=os.environ.get("MCP_TRANSPORT", "streamable-http"))
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler()],
    )

    logger.info("Starting Dummy MCP server on %s:%s (transport=%s)", args.host, args.port, args.transport)
    mcp.run(transport=args.transport, host=args.host, port=args.port)
