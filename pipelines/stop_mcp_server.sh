#!/bin/bash
# Stop MCP HTTP Server and Dify API Server
# This script stops both the MCP server and the Dify API server

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

MCP_PID_FILE="./tmp/mcp_server.pid"
DIFY_PID_FILE="./tmp/dify_api_server.pid"

echo "🛑 Stopping servers..."
echo ""

# Function to stop a server
stop_server() {
    local NAME=$1
    local PID_FILE=$2
    local PROCESS_PATTERN=$3

    echo "Stopping $NAME..."

    if [ -f "$PID_FILE" ]; then
        SERVER_PID=$(cat "$PID_FILE")

        if ps -p "$SERVER_PID" > /dev/null 2>&1; then
            kill "$SERVER_PID" 2>/dev/null

            # Wait up to 5 seconds for graceful shutdown
            for i in {1..5}; do
                if ! ps -p "$SERVER_PID" > /dev/null 2>&1; then
                    echo "   ✅ $NAME stopped gracefully"
                    rm -f "$PID_FILE"
                    return 0
                fi
                sleep 1
            done

            # Force kill if still running
            kill -9 "$SERVER_PID" 2>/dev/null
            sleep 1

            if ! ps -p "$SERVER_PID" > /dev/null 2>&1; then
                echo "   ✅ $NAME stopped (forced)"
                rm -f "$PID_FILE"
                return 0
            else
                echo "   ❌ Failed to stop $NAME"
                return 1
            fi
        else
            echo "   ⚠️  Process not running"
            rm -f "$PID_FILE"
        fi
    else
        # Try to find the process anyway
        PIDS=$(ps aux | grep "$PROCESS_PATTERN" | awk '{print $2}')

        if [ -z "$PIDS" ]; then
            echo "   ℹ️  No $NAME processes found"
        else
            echo "   Found process(es): $PIDS"
            kill $PIDS 2>/dev/null
            sleep 1

            # Force kill if still running
            for PID in $PIDS; do
                if ps -p $PID > /dev/null 2>&1; then
                    kill -9 $PID 2>/dev/null
                fi
            done
            echo "   ✅ $NAME stopped"
        fi
    fi
}

# Stop both servers
stop_server "MCP server" "$MCP_PID_FILE" "[m]cp_server_http.py"
echo ""
stop_server "Dify API server" "$DIFY_PID_FILE" "[d]ify_api_server.py"

echo ""
echo "✅ All servers stopped"
