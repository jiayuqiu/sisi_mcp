# CLAUDE.md

## Project Overview

**sisimcp** — A maritime traffic anomaly detection system exposed via MCP (Model Context Protocol) server and a FastAPI-based Dify integration API.

## Tech Stack

- Python 3.11+
- Package manager: **uv** (use `uv sync` to install deps, `uv run` to execute)
- MCP server: `fastmcp` library
- Dify API: `fastapi` + `uvicorn`
- Frontend: `fastapi` + `jinja2` (server-side rendered)
- Data processing: `pandas`, `numpy`, `ruptures`, `matplotlib`
- LLM integration: DeepSeek API
- Containerization: Docker Compose (`docker/`)

## Project Structure

```
mcp_server_http.py          # MCP HTTP server entrypoint
dify_api_server.py          # FastAPI server for Dify integration
mcp_conductor/              # Backend features (core business logic)
  entry/                    # High-level orchestration (main_traffic_detect)
  detector/                 # Detection engine & plotting
  mcp_tools/                # MCP tool definitions
  resources/                # External API clients (DeepSeek, Sisi, Dify)
frontend/                   # Web frontend (Jinja2 + FastAPI)
  app.py                    # Frontend server entrypoint (port 8003)
  templates/                # Jinja2 HTML templates (chatbot, workflow inspector)
  static/                   # CSS assets
docker/                     # Dockerfile & docker-compose.yml
pipelines/                  # Shell scripts for server management
tests/                      # Test files
```

## Common Commands

```bash
# Install dependencies
uv sync

# Run frontend locally. TODO: move into docker-compose.yml
uv run python frontend_legacy/app.py

# Run tests
uv run pytest

# Docker run MCP & Dify api server
cd docker && docker-compose build --no-cache && docker-compose up
```

## Corporate Project (Dify)

Project path: /c/Users/qiuji/codebase/dify

## Key Conventions

- Use `logging` module for all log output (not `print`), with `logger = logging.getLogger(__name__)`
- Environment variables for secrets: `DEEPSEEK_API_KEY`, `SISI_API_KEY`, `BCI_APP_ID`, `BCI_SECRET_KEY`, `BCI_BASE_URL`, `DIFY_API_KEY`, `DIFY_CHATFLOW_URL`
- Secrets are stored in `secrets/` (gitignored), loaded via `python-dotenv`
- When updating dependencies in `pyproject.toml`, always run `uv lock` to regenerate `uv.lock`
- Docker uses `uv sync --frozen --no-dev` — the lock file must be up to date before building

## Database Schema (`data/sisi.sqlite`)

```sql
-- Agent work history / DeepSeek call logs
CREATE TABLE IF NOT EXISTS log_agent_work_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    return_id TEXT UNIQUE NOT NULL,
    question_type TEXT,
    full_response TEXT,
    payload TEXT,
    run_date DATE DEFAULT (date('now')),
    run_timestamp TEXT DEFAULT (datetime('now')),
    content TEXT,
    reasoning_content TEXT
);
```

## Cross-Container Networking

- sisimcp runs in its own Docker Compose network (`docker/docker-compose.yml`)
- Dify runs in a separate project (`C:\Users\qiuji\codebase\dify\docker`)
- Use `host.docker.internal` for cross-project container communication
