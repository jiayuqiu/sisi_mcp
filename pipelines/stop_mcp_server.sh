#!/bin/bash
# Stop MCP HTTP Server and Dify API Server
# This script stops both the MCP server and the Dify API server

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Detect OS
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
    IS_WINDOWS=true
else
    IS_WINDOWS=false
fi

MCP_PID_FILE="./tmp/mcp_server.pid"
DIFY_PID_FILE="./tmp/dify_api_server.pid"

echo "🛑 Stopping servers..."
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

# Function to kill process
kill_process() {
    local pid=$1
    local force=$2
    if [ "$IS_WINDOWS" = true ]; then
        if [ "$force" = true ]; then
            taskkill //F //PID "$pid" > /dev/null 2>&1
        else
            taskkill //PID "$pid" > /dev/null 2>&1
        fi
    else
        if [ "$force" = true ]; then
            kill -9 "$pid" 2>/dev/null
        else
            kill "$pid" 2>/dev/null
        fi
    fi
}

# Function to stop a server
stop_server() {
    local NAME=$1
    local PID_FILE=$2
    local PROCESS_PATTERN=$3

    echo "Stopping $NAME..."

    if [ -f "$PID_FILE" ]; then
        SERVER_PID=$(cat "$PID_FILE")

        if check_process "$SERVER_PID"; then
            kill_process "$SERVER_PID" false

            # Wait up to 5 seconds for graceful shutdown
            for i in {1..5}; do
                if ! check_process "$SERVER_PID"; then
                    echo "   ✅ $NAME stopped gracefully"
                    rm -f "$PID_FILE"
                    return 0
                fi
                sleep 1
            done

            # Force kill if still running
            kill_process "$SERVER_PID" true
            sleep 1

            if ! check_process "$SERVER_PID"; then
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
        echo "   ℹ️  No PID file found for $NAME"
    fi
}

# Stop both servers
stop_server "MCP server" "$MCP_PID_FILE" "[m]cp_server_http.py"
echo ""
stop_server "Dify API server" "$DIFY_PID_FILE" "[d]ify_api_server.py"

echo ""
echo "✅ All servers stopped"
