# CLAUDE.md

## Project Overview

**sisimcp** — A maritime traffic anomaly detection system exposed via MCP (Model Context Protocol) server and a FastAPI-based Dify integration API.

## Tech Stack

- Python 3.11+
- Package manager: **uv** (use `uv sync` to install deps, `uv run` to execute)
- MCP server: `fastmcp` library
- Dify API: `fastapi` + `uvicorn`
- Frontend (legacy): `fastapi` + `jinja2` (server-side rendered)
- Frontend (current): `next.js` 14 + `tailwindcss` + `better-sqlite3`
- Data processing: `pandas`, `numpy`, `ruptures`, `matplotlib`
- LLM integration: DeepSeek API
- Containerization: Docker Compose (`docker/`)

## Project Structure

```
mcp_conductor/              # Backend features (core business logic)
  servers/                  # Long-running server entrypoints
    mcp_server_http.py      # MCP HTTP server entrypoint
    dify_api_server.py      # FastAPI server for Dify integration
  entry/                    # High-level orchestration (main_traffic_detect)
  detector/                 # Detection engine & plotting
  mcp_tools/                # MCP tool definitions
  resources/                # External API clients (DeepSeek, Sisi, Dify)
frontend_legacy/            # Legacy web frontend (Jinja2 + FastAPI, port 8003)
  app.py                    # Frontend server entrypoint
  templates/                # Jinja2 HTML templates (chatbot, workflow inspector)
  static/                   # CSS assets
frontend_nextjs/            # Current web frontend (Next.js 14, port 3000)
  src/app/                  # Next.js app router pages
    chatbot/                # Chatbot UI page
    workflow/               # Workflow Inspector page (reads sisi.sqlite)
    api/chat/stream/        # SSE proxy route to Dify chatflow API
    api/workflow-logs/      # API route — queries sisi.sqlite via better-sqlite3
  package.json
docker/                     # Dockerfile, Dockerfile.frontend & docker-compose.yml
pipelines/                  # Shell scripts for server management
tests/                      # Test files
```

## Common Commands

```bash
# Install dependencies
uv sync

# Run legacy frontend locally
uv run python frontend_legacy/app.py

# Run Next.js frontend locally (dev mode)
cd frontend_nextjs && npm install && npm run dev
# Available at http://localhost:3000

# Run tests
uv run pytest

# Docker: build and start all services in background (MCP + Dify API + Next.js frontend)
cd docker && docker-compose up --build -d

# Docker: rebuild everything from scratch (no cache)
cd docker && docker-compose down && docker-compose build --no-cache && docker-compose up -d

# Docker: view logs for a specific service
cd docker && docker-compose logs -f frontend_nextjs

# Docker: check running containers
cd docker && docker-compose ps
```

## Corporate Project (Dify)

Project path: /c/Users/qiuji/codebase/dify

## Key Conventions

- Use `logging` module for all log output (not `print`), with `logger = logging.getLogger(__name__)`
- Environment variables for secrets: `DEEPSEEK_API_KEY`, `SISI_API_KEY`, `BCI_APP_ID`, `BCI_SECRET_KEY`, `BCI_BASE_URL`, `DIFY_API_KEY`, `DIFY_CHATFLOW_URL`
- Secrets are stored in `secrets/` (gitignored), loaded via `python-dotenv`
- When updating dependencies in `pyproject.toml`, always run `uv lock` to regenerate `uv.lock`
- Docker uses `uv sync --frozen --no-dev` — the lock file must be up to date before building
- `better-sqlite3` is a native Node.js addon — it must be compiled inside the Docker container (Linux), NOT copied from the host `node_modules` (Windows). The `.dockerignore` at the project root excludes `frontend_nextjs/node_modules` and `frontend_nextjs/.next` to ensure this. Never remove those entries.
- Next.js frontend env vars: `DIFY_API_KEY`, `DIFY_CHATFLOW_URL`, `SQLITE_DB_PATH` (defaults to `../data/sisi.sqlite`). In Docker, `SQLITE_DB_PATH=/app/data/sisi.sqlite` with the `../data` volume mounted.

## Database Schema (`data/sisi.sqlite`)

`mcp_conductor/entry/main_setup_schema.py` is the source of truth — run it to create or
update the database. The tables the sync writes to:

```sql
-- Daily metrics per shipping channel (strait / canal)
CREATE TABLE IF NOT EXISTS ship_cnt_in_pipe (
    pipe_name TEXT,             -- Name of the channel (e.g., '马六甲海峡')
    date_id INTEGER,            -- Date in YYYYMMDD format
    ship_cnt INTEGER,           -- Number of ships passing the strait
    duration REAL,              -- Time of ships passing the strait
    detection_flag TEXT,        -- Anomaly marker (e.g., '红') or NULL; legacy, not written by current code
    PRIMARY KEY (pipe_name, date_id)
);

-- Daily metrics per port (same shape, keyed on port_name)
CREATE TABLE IF NOT EXISTS ship_cnt_in_port (
    port_name TEXT,             -- Name of the port (e.g., '鹿特丹港')
    date_id INTEGER,
    ship_cnt INTEGER,           -- Number of ships berthing in the port
    duration REAL,              -- Time of ships berthing in the port
    detection_flag TEXT,
    PRIMARY KEY (port_name, date_id)
);

-- Agent work history / DeepSeek call logs
CREATE TABLE IF NOT EXISTS log_agent_worklog (
    return_id TEXT UNIQUE NOT NULL,
    question_type TEXT,
    full_response TEXT,
    payload TEXT,
    date_id INT,
    pipe_name TEXT,
    run_timestamp TEXT DEFAULT (datetime('now')),
    content TEXT,
    reasoning_content TEXT,
    PRIMARY KEY (pipe_name, date_id, run_timestamp)
);
```

Also created by `setup_schema()`: `m_pipe_anomaly_roll_percentile`,
`m_roll_percentile_parameter`, `dim_anomaly_flag` (seeded from
`ROLLING_PERCENTILE_FLAG`), and the view `vw_m_pipe_anomaly_roll_percentile`.

`m_roll_percentile_parameter` holds the frozen detection bounds per
`(location_type, location_name, metric, valid_from_date_id)` — the detector reads them
instead of recomputing quantiles per run. Rows with `is_locked = 1` are manual overrides
and must not be overwritten by the refit job. See
`docs/plan-duration-aware-detector.md`.

`sail_time_in_pipe` is a legacy import from 中国航运数据库 (2023–2025), not created or
written by any code. Do not confuse it with `ship_cnt_in_pipe.duration`.

### BCI metric routing (`zbxx`)

The BCI API returns a `zbxx` field on each result item identifying the metric. Two
metrics share one row, so `main_sync_bci_data.py` routes **per item** via `ZBXX_ROUTES`:

| `zbxx` | Table | Column |
|---|---|---|
| 101-0001 | `ship_cnt_in_port` | `ship_cnt` |
| 101-0002 | `ship_cnt_in_port` | `duration` |
| 101-0003 | `ship_cnt_in_pipe` | `ship_cnt` |
| 101-0004 | `ship_cnt_in_pipe` | `duration` |

The request groups (`101-0003,101-0004`) are API batching only and must **not** be used
to pick the target table. Writes use `INSERT ... ON CONFLICT ... DO UPDATE` on a single
column: `INSERT OR REPLACE` would delete the row and null out the sibling metric.

## Cross-Container Networking

- sisimcp runs in its own Docker Compose network (`docker/docker-compose.yml`)
- Dify runs in a separate project (`C:\Users\qiuji\codebase\dify\docker`)
- Use `host.docker.internal` for cross-project container communication
