#!/bin/bash
# Test script for Dify MCP Integration

echo "🧪 Testing Dify MCP Integration..."
echo ""

# Test 1: Health check
echo "1️⃣  Testing health endpoint..."
response=$(curl -s http://localhost:8001/health)
if [ $? -eq 0 ]; then
    echo "   ✅ Health check passed: $response"
else
    echo "   ❌ Health check failed"
    exit 1
fi
echo ""

# Test 2: Detect congestion
echo "2️⃣  Testing detect_congestion API..."
response=$(curl -s -X POST http://localhost:8001/api/detect_congestion \
    -H "Content-Type: application/json" \
    -d '{"question": "2023年12月 曼德海峡是否发生异常？"}')
if [ $? -eq 0 ]; then
    echo "   ✅ Detect congestion test passed"
    echo "   Response: $response" | head -c 200
    echo "..."
else
    echo "   ❌ Detect congestion test failed"
fi
echo ""

# Test 3: Ask question
echo "3️⃣  Testing ask_question API..."
response=$(curl -s -X POST http://localhost:8001/api/ask_question \
    -H "Content-Type: application/json" \
    -d '{"question": "2023年12月 曼德海峡是否发生异常？"}')
if [ $? -eq 0 ]; then
    echo "   ✅ Ask question test passed"
    echo "   Response: $response" | head -c 200
    echo "..."
else
    echo "   ❌ Ask question test failed"
fi
echo ""

# Test 4: Plot analysis
echo "4️⃣  Testing plot_analysis API..."
response=$(curl -s -X POST http://localhost:8001/api/plot_analysis \
    -H "Content-Type: application/json" \
    -d '{"run_date": "2023-12-31", "pipe_name": "曼德海峡"}')
if [ $? -eq 0 ]; then
    echo "   ✅ Plot analysis test passed"
    echo "   Response: $response" | head -c 200
    echo "..."
else
    echo "   ❌ Plot analysis test failed"
fi
echo ""

echo "✅ All tests completed!"
echo ""
echo "📋 Now you can use these URLs in Dify:"
echo "   http://localhost:8001/api/detect_congestion"
echo "   http://localhost:8001/api/ask_question"
echo "   http://localhost:8001/api/plot_analysis"
