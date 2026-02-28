#!/usr/bin/env python3
"""
Frontend Web Server
Serves the chatbot and workflow inspector pages via Jinja2 templates.
Also exposes a streaming SSE proxy for the Next.js frontend.
"""
import os
import logging
import sqlite3
import json
from pathlib import Path
from typing import AsyncGenerator

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("frontend")

DIFY_API_KEY = os.getenv("DIFY_API_KEY", "")
DIFY_CHATFLOW_URL = os.getenv("DIFY_CHATFLOW_URL", "https://api.dify.ai/v1")
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "sisi.sqlite"

app = FastAPI(title="SisiMCP Frontend")

# Allow Next.js dev server to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_dir = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=frontend_dir / "static"), name="static")
templates = Jinja2Templates(directory=frontend_dir / "templates")


# ── Page Routes ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return RedirectResponse(url="/chatbot")


@app.get("/chatbot", response_class=HTMLResponse)
async def chatbot_page(request: Request):
    return templates.TemplateResponse("chatbot.html", {"request": request})


@app.get("/workflow", response_class=HTMLResponse)
async def workflow_page(request: Request):
    return templates.TemplateResponse("workflow.html", {"request": request})


# ── API Routes ───────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    conversation_id: str = ""


@app.post("/api/chat")
async def chat_proxy(req: ChatRequest):
    """Proxy chat requests to Dify chatflow API (keeps API key server-side)."""
    if not DIFY_API_KEY:
        return {"error": "DIFY_API_KEY not configured"}

    url = f"{DIFY_CHATFLOW_URL}/chat-messages"
    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "inputs": {},
        "query": req.message,
        "response_mode": "blocking",
        "conversation_id": req.conversation_id,
        "user": "web-user",
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return {
            "answer": data.get("answer", ""),
            "conversation_id": data.get("conversation_id", ""),
        }
    except requests.exceptions.RequestException as e:
        logger.error(f"Dify API error: {e}")
        return {"error": str(e)}


@app.post("/api/chat/stream")
async def chat_stream_proxy(req: ChatRequest):
    """Proxy chat requests to Dify chatflow API in streaming (SSE) mode."""
    if not DIFY_API_KEY:
        async def err():
            yield f"data: {json.dumps({'event': 'error', 'message': 'DIFY_API_KEY not configured'})}\n\n"
        return StreamingResponse(err(), media_type="text/event-stream")

    url = f"{DIFY_CHATFLOW_URL}/chat-messages"
    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "inputs": {},
        "query": req.message,
        "response_mode": "streaming",
        "conversation_id": req.conversation_id,
        "user": "web-user",
    }

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            with requests.post(url, json=payload, headers=headers, stream=True, timeout=120) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if line:
                        decoded = line.decode("utf-8") if isinstance(line, bytes) else line
                        yield f"{decoded}\n\n"
        except Exception as e:
            logger.error(f"Dify streaming error: {e}")
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/workflow-logs")
async def get_workflow_logs(limit: int = 50, offset: int = 0):
    """Fetch workflow logs from SQLite."""
    if not DB_PATH.exists():
        return {"logs": [], "total": 0}

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Check if table exists
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='log_agent_work_history'"
    )
    if not cursor.fetchone():
        conn.close()
        return {"logs": [], "total": 0}

    cursor.execute("SELECT COUNT(*) FROM log_agent_work_history")
    total = cursor.fetchone()[0]

    cursor.execute(
        "SELECT id, question_type, run_date, content, reasoning_content FROM log_agent_work_history ORDER BY run_timestamp DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    logs = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return {"logs": logs, "total": total}


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "SisiMCP Frontend"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
