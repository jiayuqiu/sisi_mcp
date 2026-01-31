#!/bin/bash
# Setup script for Dify MCP Integration

echo "🚀 Starting MCP Server and Dify Wrapper..."
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 is not installed"
    exit 1
fi

# Install dependencies if needed
echo "📦 Checking dependencies..."
pip install -q fastapi uvicorn httpx fastmcp || {
    echo "❌ Failed to install dependencies"
    exit 1
}

# Create tmp directories
mkdir -p ./tmp/images
mkdir -p ./tmp

echo "✅ Dependencies ready"
echo ""

# Start MCP server in background
echo "🔧 Starting MCP HTTP Server on port 8000..."
python3 mcp_server_http.py > ./tmp/mcp_server.log 2>&1 &
MCP_PID=$!
echo "   PID: $MCP_PID"

# Wait for MCP server to start
sleep 2

# Start Dify wrapper in background
echo "🔧 Starting Dify Wrapper on port 8001..."
python3 dify_wrapper.py > ./tmp/dify_wrapper.log 2>&1 &
WRAPPER_PID=$!
echo "   PID: $WRAPPER_PID"

# Wait for wrapper to start
sleep 2

echo ""
echo "✅ Servers are running!"
echo ""
echo "📋 Server Information:"
echo "   MCP Server:    http://localhost:8000"
echo "   Dify Wrapper:  http://localhost:8001"
echo "   Health Check:  http://localhost:8001/health"
echo ""
echo "📝 Process IDs:"
echo "   MCP Server PID:    $MCP_PID"
echo "   Dify Wrapper PID:  $WRAPPER_PID"
echo ""
echo "📄 Logs:"
echo "   MCP Server:    tail -f ./tmp/mcp_server.log"
echo "   Dify Wrapper:  tail -f ./tmp/dify_wrapper.log"
echo ""
echo "🛑 To stop servers:"
echo "   kill $MCP_PID $WRAPPER_PID"
echo ""
echo "🔗 Dify Tool URLs (use these in Dify):"
echo "   - If Dify is local:"
echo "     http://localhost:8001/api/detect_congestion"
echo "     http://localhost:8001/api/ask_question"
echo "     http://localhost:8001/api/plot_analysis"
echo ""
echo "   - If Dify is in Docker:"
echo "     http://host.docker.internal:8001/api/detect_congestion"
echo "     http://host.docker.internal:8001/api/ask_question"
echo "     http://host.docker.internal:8001/api/plot_analysis"
echo ""
echo "✨ Ready for Dify integration!"
