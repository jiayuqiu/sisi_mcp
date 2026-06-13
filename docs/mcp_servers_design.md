# MCP Servers Design

## Directory Structure

```
mcp_servers/                          # Root: all MCP server definitions live here
├── __init__.py                       # Package marker
│
├── base/                             # Shared base classes & utilities
│   ├── __init__.py
│   └── server.py                     # BaseMCPServer — common config, logging, lifecycle
│
├── local/                            # Local tools (DB, API, documents)
│   ├── __init__.py
│   ├── db_tools.py                   # Tools backed by SQLite / DuckDB / Postgres
│   ├── api_tools.py                  # Tools that wrap internal REST / gRPC endpoints
│   └── doc_tools.py                  # Tools that search/query local documents (Markdown, PDF, etc.)
│
├── external/                         # External MCP server clients
│   ├── __init__.py
│   └── client.py                     # MCPClient — connect, list tools, call tools on remote MCP servers
│
├── scripts/                          # Runnable MCP server entrypoints (one script = one server)
│   ├── dummy_mcp.py                  # Dummy MCP server (starter template)
│   └── traffic_mcp.py                # (future) Full traffic-detection MCP server
│
└── config.py                         # Shared configuration (env vars, defaults, constants)
```

---

## Design Principles

### 1. Single-script MCP servers

Each MCP server lives in **one script** under `scripts/`. It instantiates a `FastMCP`, decorates tools with `@mcp.tool()`, and calls `mcp.run()` at the bottom. No external project imports needed for the dummy server — it is fully self-contained.

### 2. Tool categories

| Category | Location | Description |
|----------|----------|-------------|
| **Local** | `local/db_tools.py` | Query local databases (SQLite, DuckDB). Wrap results as structured JSON/CSV. |
| **Local** | `local/api_tools.py` | Call internal REST endpoints. Handle auth, pagination, error mapping. |
| **Local** | `local/doc_tools.py` | Search local file system documents. Use simple `grep`-like or embedding-based retrieval. |
| **External** | `external/client.py` | Connect to remote MCP servers via `mcp.ClientSession`. List their tools, forward calls, merge results. |

### 3. Dummy-first approach

`scripts/dummy_mcp.py` is a working template with:
- Two local tools (echo + time)
- One external MCP tool placeholder
- No project-internal imports — pure `fastmcp` + stdlib
- Ready to run off `uv run python mcp_servers/scripts/dummy_mcp.py`

---

## Core Components

### `scripts/dummy_mcp.py` — Starter Template

```python
"""Dummy MCP Server — starter template for new MCP servers."""
import asyncio
import json
import logging
import os
from datetime import datetime

from fastmcp import FastMCP

logger = logging.getLogger("dummy_mcp")
mcp = FastMCP("dummy-server")

# ── Local Tools ──────────────────────────────────────────

@mcp.tool()
async def echo(message: str) -> str:
    """Echo the input message back."""
    ...

@mcp.tool()
async def get_current_time() -> str:
    """Return the current server time in ISO format."""
    ...

@mcp.tool()
async def query_local_db(query: str) -> str:
    """Run a read-only SQL query against the local SQLite database."""
    ...

@mcp.tool()
async def read_local_doc(path: str) -> str:
    """Read the contents of a local document file."""
    ...

# ── External MCP Tool ────────────────────────────────────

@mcp.tool()
async def invoke_external_mcp(server_name: str, tool_name: str,
                               arguments: str) -> str:
    """Invoke a tool on an external MCP server."""
    ...

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8001)
```

### `local/db_tools.py`

```python
def make_db_query_tool(db_path: str) -> callable:
    """Factory that returns a @mcp.tool() for the given DB."""
    ...

def make_db_schema_tool(db_path: str) -> callable:
    """Return a tool that lists all tables and their schemas."""
    ...
```

### `local/api_tools.py`

```python
def make_api_tool(name: str, endpoint: str, method: str = "GET") -> callable:
    """Factory that wraps an internal REST endpoint as an MCP tool."""
    ...
```

### `external/client.py`

```python
class ExternalMCPClient:
    """Connect to remote MCP servers using the mcp library."""

    async def connect(self, server_url: str) -> None: ...
    async def list_tools(self) -> list[dict]: ...
    async def call_tool(self, name: str, args: dict) -> str: ...
    async def disconnect(self) -> None: ...
```

---

## One-File MCP Script Pattern (Dummy)

The dummy server follows this minimal pattern — everything in one file, zero external imports:

```
1. Imports          (fastmcp, stdlib only)
2. Logging config   (stderr + optional file)
3. FastMCP instance
4. @mcp.tool() definitions
   ├── local tools  (echo, time, db, docs)
   └── external tool (remote MCP invocation)
5. if __name__ == "__main__": mcp.run()
```

---

## Port Allocation

| Server | Port | Description |
|--------|------|-------------|
| `dummy_mcp.py` | 8001 | Dummy template |
| `traffic_mcp.py` | 8002 | (future) Full traffic MCP |
| (existing) `mcp_server_http.py` | 8000 | Legacy MCP server |

---

## Quick Start

```bash
# Run the dummy MCP server
uv run python mcp_servers/scripts/dummy_mcp.py

# Or with custom host/port
uv run python mcp_servers/scripts/dummy_mcp.py --host 127.0.0.1 --port 9000

# Test with an MCP client (e.g., Claude Desktop, VS Code Copilot)
# Configure the client to connect to http://127.0.0.1:8001/sse
```

---

## Future: `scripts/traffic_mcp.py` (Example)

When the dummy is validated, the traffic-detection MCP server would combine **all** tools in a single script:

```python
# scripts/traffic_mcp.py
mcp = FastMCP("traffic-detection")

# Local tools
@mcp.tool()  # from local/db_tools.py
async def query_ship_counts(pipe_name: str, date_from: int, date_to: int) -> str: ...

@mcp.tool()  # from local/api_tools.py
async def detect_anomaly(pipe_name: str, date_id: int) -> str: ...

@mcp.tool()  # from local/doc_tools.py
async def search_shipping_docs(keyword: str) -> str: ...

# External tools
@mcp.tool()  # via external/client.py
async def ask_deepseek(question: str) -> str: ...
```
