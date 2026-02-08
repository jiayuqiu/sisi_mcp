#!/bin/bash
# Test script for Dify MCP Integration

echo "🧪 Testing Dify MCP Integration..."
echo ""

# Test 1: Health check
echo "1️⃣  Testing health endpoint..."
response=$(curl -s http://localhost:8002/health)
if [ $? -eq 0 ]; then
    echo "   ✅ Health check passed: $response"
else
    echo "   ❌ Health check failed"
    exit 1
fi
echo ""

# Test 2: Detect congestion
echo "2️⃣  Testing detect_anomaly API..."
response=$(curl -s -X POST http://localhost:8002/api/detect_anomaly \
    -H "Content-Type: application/json" \
    -d '{"question": "2023年12月 曼德海峡是否发生异常？"}')
if [ $? -eq 0 ]; then
    echo "   ✅ Detect anomaly test passed"
    echo "   Response: $response" | head -c 200
    echo "..."
else
    echo "   ❌ Detect anomaly test failed"
fi
echo ""

# Test 3: Ask question
echo "3️⃣  Testing analyze_anomaly_reason API..."
response=$(curl -s -X POST http://localhost:8002/api/analyze_anomaly_reason \
    -H "Content-Type: application/json" \
    -d '{"question": "2023年12月 曼德海峡是否发生异常？"}')
if [ $? -eq 0 ]; then
    echo "   ✅ Analyze anomaly reason test passed"
    echo "   Response: $response" | head -c 200
    echo "..."
else
    echo "   ❌ Analyze anomaly reason test failed"
fi
echo ""

# Test 4: Plot analysis
echo "4️⃣  Testing plot_analysis API..."
response=$(curl -s -X POST http://localhost:8002/api/plot_analysis \
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
echo "   http://localhost:8002/api/detect_anomaly"
echo "   http://localhost:8002/api/analyze_anomaly_reason"
echo "   http://localhost:8002/api/plot_analysis"
