#!/usr/bin/env python3
"""
MCP Server for Traffic Detection (HTTP)
Exposes traffic detection functionality as tools that can be called via HTTP.
Uses fastmcp for HTTP server support.
"""
import logging
import asyncio
import os
import argparse
import json
import urllib.request
import urllib.error
from fastmcp import FastMCP

# Configure logging to output to both file and stderr
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),  # stderr
        logging.FileHandler("/tmp/mcp_server.log", mode="a", encoding="utf-8")
    ]
)
logger = logging.getLogger("mcp_server")


# Create the FastMCP server instance
mcp = FastMCP("traffic-detection-server")


def _invoke_dify_chatflow(question: str) -> str:
    """Invoke the configured Dify chatflow endpoint in blocking mode.

    TODO:
    - Add bounded retries and configurable timeout/backoff.
    - Return a normalized response envelope for MCP clients.
    - Include request_id propagation for end-to-end tracing.
    """
    chatflow_url = os.environ.get("DIFY_CHATFLOW_URL", "").strip()
    api_key = os.environ.get("DIFY_API_KEY", "").strip()

    if not chatflow_url:
        return "DIFY_CHATFLOW_URL is not configured."
    if not api_key:
        return "DIFY_API_KEY is not configured."

    payload = {
        "inputs": {},
        "query": question,
        "response_mode": "blocking",
        "user": "mcp-server",
    }

    req = urllib.request.Request(
        chatflow_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=120) as resp:
        body = resp.read().decode("utf-8")
        result = json.loads(body)

    answer = result.get("answer")
    if isinstance(answer, str) and answer.strip():
        return answer.strip()

    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def dify_chatbot(question: str) -> str:
    """Forward user question to the configured Dify chatbot/chatflow and return its answer.

    TODO:
    - Validate input/output against a frozen v1 schema.
    - Return structured errors with stable error codes.
    - Keep tool contract backward compatible for Dify integration.
    - 支持中文
    """
    if not question or not question.strip():
        return "Error: Missing question parameter."

    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, _invoke_dify_chatflow, question.strip())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        return f"Dify HTTP error: {e.code} {e.reason}\n{detail}"
    except Exception as e:
        return f"Dify invocation failed: {str(e)}"


@mcp.tool()
async def other_mcp_server(request: str) -> str:
    """Placeholder tool for future external MCP server routing.

    TODO:
    - Implement target-based routing to external MCP servers.
    - Normalize external responses into a single MCP format.
    - Add auth, timeout, and allowlist controls per target.
    - 支持中文
    """
    return (
        "Placeholder: external MCP server routing is not implemented yet.\n"
        f"request={request}"
    )


if __name__ == "__main__":
        """Run the MCP server over HTTP.

        Host and port can be set via environment variables or CLI args:
            MCP_HOST / --host   (default: 0.0.0.0)
            MCP_PORT / --port   (default: 8000)
            MCP_TRANSPORT / --transport (default: streamable-http)
        """
        parser = argparse.ArgumentParser()
        parser.add_argument("--host", default=os.environ.get("MCP_HOST", "0.0.0.0"),
                                                help="Host to bind the server to (default: 0.0.0.0)")
        parser.add_argument("--port", type=int, default=int(os.environ.get("MCP_PORT", "8000")),
                                                help="Port to bind the server to (default: 8000)")
        parser.add_argument("--transport", default=os.environ.get("MCP_TRANSPORT", "streamable-http"),
                                                help="Transport to use for FastMCP (default: streamable-http)")
        args = parser.parse_args()

        logger.info(f"✅ MCP HTTP server starting on {args.host}:{args.port} (transport={args.transport})...")
        # Run with streamable-http transport for modern HTTP support
        # Available transports: "stdio", "sse", "streamable-http"
        mcp.run(transport=args.transport, host=args.host, port=args.port)
