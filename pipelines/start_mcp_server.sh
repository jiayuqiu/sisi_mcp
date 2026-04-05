#!/bin/bash
# Start MCP HTTP Server and Dify API Server
# This script starts both the MCP server and the Dify API server

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Detect OS and set Python command
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
    IS_WINDOWS=true
    PYTHON_CMD="python"
else
    IS_WINDOWS=false
    PYTHON_CMD="python3"
fi

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    if [ "$IS_WINDOWS" = true ]; then
        source .venv/Scripts/activate
    else
        source .venv/bin/activate
    fi
fi

# Configuration
MCP_HOST="${MCP_HOST:-0.0.0.0}"
MCP_PORT="${MCP_PORT:-8000}"
DIFY_HOST="${DIFY_HOST:-0.0.0.0}"
DIFY_PORT="${DIFY_PORT:-8002}"
TRANSPORT="${MCP_TRANSPORT:-streamable-http}"

MCP_LOG_FILE="./tmp/mcp_server.log"
MCP_PID_FILE="./tmp/mcp_server.pid"
DIFY_LOG_FILE="./tmp/dify_api_server.log"
DIFY_PID_FILE="./tmp/dify_api_server.pid"

# Ensure tmp directory exists
mkdir -p ./tmp

echo "🚀 Starting servers..."
echo ""

# Function to check if process is running
check_process() {
    local pid=$1
    if [ "$IS_WINDOWS" = true ]; then
        tasklist //FI "PID eq $pid" 2>/dev/null | grep -q "$pid"
    else
        ps -p "$pid" > /dev/null 2>&1
    fi
}

# Start MCP server
echo "1️⃣  Starting MCP HTTP Server..."
if [ -f "$MCP_PID_FILE" ]; then
    OLD_PID=$(cat "$MCP_PID_FILE")
    if check_process "$OLD_PID"; then
        echo "   ⚠️  MCP server already running (PID: $OLD_PID)"
    else
        rm -f "$MCP_PID_FILE"
    fi
fi

if [ ! -f "$MCP_PID_FILE" ]; then
    $PYTHON_CMD mcp_conductor/servers/mcp_server_http.py \
        --host "$MCP_HOST" \
        --port "$MCP_PORT" \
        --transport "$TRANSPORT" \
        >> "$MCP_LOG_FILE" 2>&1 &

    MCP_PID=$!
    echo $MCP_PID > "$MCP_PID_FILE"
    sleep 2

    if check_process $MCP_PID; then
        echo "   ✅ MCP server started (PID: $MCP_PID)"
        echo "      URL: http://$MCP_HOST:$MCP_PORT"
    else
        echo "   ❌ Failed to start MCP server"
        rm -f "$MCP_PID_FILE"
    fi
fi

echo ""

# Start Dify API server
echo "2️⃣  Starting Dify API Server..."
if [ -f "$DIFY_PID_FILE" ]; then
    OLD_PID=$(cat "$DIFY_PID_FILE")
    if check_process "$OLD_PID"; then
        echo "   ⚠️  Dify API server already running (PID: $OLD_PID)"
    else
        rm -f "$DIFY_PID_FILE"
    fi
fi

if [ ! -f "$DIFY_PID_FILE" ]; then
    $PYTHON_CMD mcp_conductor/servers/dify_api_server.py >> "$DIFY_LOG_FILE" 2>&1 &

    DIFY_PID=$!
    echo $DIFY_PID > "$DIFY_PID_FILE"
    sleep 2

    if check_process $DIFY_PID; then
        echo "   ✅ Dify API server started (PID: $DIFY_PID)"
        echo "      URL: http://$DIFY_HOST:$DIFY_PORT"
    else
        echo "   ❌ Failed to start Dify API server"
        rm -f "$DIFY_PID_FILE"
    fi
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Server Status"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "MCP Server:       http://$MCP_HOST:$MCP_PORT"
echo "Dify API Server:  http://$DIFY_HOST:$DIFY_PORT"
echo ""
echo "Logs:"
echo "  MCP:  tail -f $MCP_LOG_FILE"
echo "  Dify: tail -f $DIFY_LOG_FILE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"