#!/bin/bash
# Restart MCP HTTP Server and Dify API Server
# This script stops and then starts both servers

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "🔄 Restarting MCP and Dify API servers..."
echo ""

# Stop the servers
bash "$SCRIPT_DIR/stop_mcp_server.sh"

echo ""
echo "⏳ Waiting 2 seconds before restart..."
sleep 2
echo ""

# Start the servers
bash "$SCRIPT_DIR/start_mcp_server.sh"

echo ""
echo "✅ Restart complete!"
