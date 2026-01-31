#!/usr/bin/env python3
"""
Dify Integration Wrapper for MCP Server
Provides RESTful endpoints that Dify can easily consume
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import logging

app = FastAPI(title="Dify MCP Wrapper")
logger = logging.getLogger(__name__)

# Add CORS middleware for Dify access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your Dify domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MCP server endpoint
MCP_BASE_URL = "http://localhost:8000"


class QuestionRequest(BaseModel):
    question: str


class PlotRequest(BaseModel):
    run_date: str
    pipe_name: str


async def call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    """Call an MCP tool using JSON-RPC protocol"""
    async with httpx.AsyncClient() as client:
        # MCP uses JSON-RPC 2.0 protocol
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        response = await client.post(
            f"{MCP_BASE_URL}/mcp",
            json=payload,
            headers={"Accept": "application/json"},
            timeout=60.0
        )
        response.raise_for_status()
        result = response.json()

        # Extract the actual result from JSON-RPC response
        if "result" in result:
            return result["result"]
        elif "error" in result:
            raise HTTPException(status_code=500, detail=result["error"].get("message", "MCP tool error"))
        return result


@app.post("/api/detect_congestion")
async def detect_congestion(request: QuestionRequest):
    """Wrapper for detect_traffic_congestion tool"""
    try:
        result = await call_mcp_tool(
            "detect_traffic_congestion",
            {"question": request.question}
        )
        return {"result": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calling detect_congestion: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ask_question")
async def ask_question(request: QuestionRequest):
    """Wrapper for ask_traffic_question tool"""
    try:
        result = await call_mcp_tool(
            "ask_traffic_question",
            {"question": request.question}
        )
        return {"result": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calling ask_question: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/plot_analysis")
async def plot_analysis(request: PlotRequest):
    """Wrapper for plot_ship_congestion_analysis tool"""
    try:
        result = await call_mcp_tool(
            "plot_ship_congestion_analysis",
            {
                "run_date": request.run_date,
                "pipe_name": request.pipe_name
            }
        )
        return {"result": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calling plot_analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "mcp_server": MCP_BASE_URL}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)