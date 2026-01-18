#!/usr/bin/env python3
"""
Test client for the MCP HTTP server.
Demonstrates how to call the traffic detection tools via HTTP.
"""
import requests
import json


def test_detect_congestion():
    """Test the detect_traffic_congestion tool."""
    print("=" * 60)
    print("Testing detect_traffic_congestion...")
    print("=" * 60)
    
    url = "http://localhost:8000/tools/detect_traffic_congestion"
    payload = {
        "question": "2023年12月 曼德海峡是否发生异常?"
    }
    
    response = requests.post(url, json=payload)
    print(f"Status Code: {response.status_code}")
    print(f"Response:\n{response.text}\n")


def test_ask_traffic_question():
    """Test the ask_traffic_question tool."""
    print("=" * 60)
    print("Testing ask_traffic_question...")
    print("=" * 60)
    
    url = "http://localhost:8000/tools/ask_traffic_question"
    payload = {
        "question": "请分析2023年12月曼德海峡发生异常的原因"
    }
    
    response = requests.post(url, json=payload)
    print(f"Status Code: {response.status_code}")
    print(f"Response:\n{response.text}\n")


def test_plot_congestion():
    """Test the plot_ship_congestion_analysis tool."""
    print("=" * 60)
    print("Testing plot_ship_congestion_analysis...")
    print("=" * 60)
    
    url = "http://localhost:8000/tools/plot_ship_congestion_analysis"
    payload = {
        "run_date": "2023-12-31",
        "pipe_name": "曼德海峡"
    }
    
    response = requests.post(url, json=payload)
    print(f"Status Code: {response.status_code}")
    print(f"Response:\n{response.text}\n")


def list_tools():
    """List all available tools."""
    print("=" * 60)
    print("Listing all available tools...")
    print("=" * 60)
    
    url = "http://localhost:8000/tools"
    
    response = requests.get(url)
    print(f"Status Code: {response.status_code}")
    print(f"Available Tools:")
    tools = response.json()
    for tool in tools:
        print(f"  - {tool.get('name', 'N/A')}: {tool.get('description', 'N/A')[:100]}...")
    print()


if __name__ == "__main__":
    print("\n🚀 MCP HTTP Server Test Client\n")
    
    try:
        # First, list all tools
        list_tools()
        
        # Test each tool
        test_detect_congestion()
        test_ask_traffic_question()
        test_plot_congestion()
        
        print("✅ All tests completed!")
        
    except requests.exceptions.ConnectionError:
        print("❌ Error: Cannot connect to server.")
        print("Please make sure the MCP server is running on http://localhost:8000")
        print("Run: python mcp_server_http.py")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
