#!/usr/bin/env python3
"""
MCP Client for Traffic Detection
Uses httpx to interact with the MCP HTTP server via JSON-RPC 2.0.
"""
import httpx
import json
import asyncio
from typing import Any, Dict, Optional
import argparse


class MCPClient:
    """Client for interacting with MCP server via HTTP using JSON-RPC 2.0"""
    
    def __init__(self, base_url: str = "http://localhost:8000", transport: str = "sse"):
        """Initialize MCP client
        
        Args:
            base_url: Base URL of the MCP server
            transport: Transport type (sse or streamable-http)
        """
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        
        # Set endpoint based on transport type
        if transport == "sse":
            self.endpoint = f"{self.base_url}/sse"
        else:  # streamable-http
            self.endpoint = f"{self.base_url}/message"
        
        self.request_id = 0
        self.client = httpx.AsyncClient(timeout=300.0)  # 5 minute timeout
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    def _next_request_id(self) -> int:
        """Generate next request ID"""
        self.request_id += 1
        return self.request_id
    
    async def _send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send JSON-RPC 2.0 request to MCP server
        
        Args:
            method: JSON-RPC method name (e.g., "tools/list", "tools/call")
            params: Method parameters
            
        Returns:
            JSON-RPC response
        """
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": self._next_request_id()
        }
        
        response = await self.client.post(
            self.endpoint,
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        return response.json()
    
    async def list_tools(self) -> Dict[str, Any]:
        """List all available tools on the MCP server
        
        Returns:
            Dictionary containing tools information
        """
        return await self._send_request("tools/list")
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Call a tool on the MCP server
        
        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments
            
        Returns:
            Tool result as text
        """
        response = await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
        
        # Extract text content from response
        if "result" in response:
            result = response["result"]
            if isinstance(result, dict) and "content" in result:
                # Extract text from content array
                text_parts = []
                for content in result["content"]:
                    if content.get("type") == "text":
                        text_parts.append(content.get("text", ""))
                return "\n".join(text_parts)
            return str(result)
        elif "error" in response:
            error = response["error"]
            return f"Error: {error.get('message', str(error))}"
        
        return str(response)
    
    async def detect_traffic_congestion(self, question: str) -> str:
        """Detect traffic congestion
        
        Args:
            question: Question in Chinese (e.g., "2023年12月 曼德海峡是否发生异常?")
            
        Returns:
            Detection result
        """
        return await self.call_tool("detect_traffic_congestion", {"question": question})
    
    async def ask_traffic_question(self, question: str) -> str:
        """Ask detailed traffic analysis question
        
        Args:
            question: Question in Chinese (e.g., "请分析2023年12月曼德海峡发生异常的原因")
            
        Returns:
            Detailed analysis result
        """
        return await self.call_tool("ask_traffic_question", {"question": question})
    
    async def plot_ship_congestion_analysis(self, run_date: str, pipe_name: str) -> str:
        """Plot ship congestion analysis
        
        Args:
            run_date: End date for analysis (YYYY-MM-DD)
            pipe_name: Channel name (马六甲海峡, 曼德海峡, 马六甲)
            
        Returns:
            Plot result with image path
        """
        return await self.call_tool("plot_ship_congestion_analysis", {
            "run_date": run_date,
            "pipe_name": pipe_name
        })


async def main():
    """Example usage of MCP client"""
    parser = argparse.ArgumentParser(description="MCP Client for Traffic Detection")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000",
                        help="Base URL of MCP server (default: http://127.0.0.1:8000)")
    parser.add_argument("--transport", default="streamable-http",
                        help="Transport type: sse or streamable-http (default: streamable-http)")
    parser.add_argument("--test", action="store_true",
                        help="Run all test cases")
    args = parser.parse_args()
    
    async with MCPClient(base_url=args.base_url, transport=args.transport) as client:
        print(f"🚀 MCP Client connected to {args.base_url}")
        print(f"🔗 Transport: {args.transport}")
        print(f"📡 Endpoint: {client.endpoint}\n")
        
        if args.test:
            # Test 1: List all tools
            print("=" * 70)
            print("TEST 1: Listing all available tools")
            print("=" * 70)
            try:
                tools = await client.list_tools()
                print(json.dumps(tools, indent=2, ensure_ascii=False))
            except Exception as e:
                print(f"❌ Error: {e}")
            
            print("\n")
            
            # Test 2: Detect traffic congestion
            print("=" * 70)
            print("TEST 2: Detecting traffic congestion")
            print("=" * 70)
            try:
                result = await client.detect_traffic_congestion(
                    "2023年12月 曼德海峡是否发生异常?"
                )
                print("📄 Result:")
                print(result)
            except Exception as e:
                print(f"❌ Error: {e}")
            
            print("\n")
            
            # Test 3: Ask detailed question
            print("=" * 70)
            print("TEST 3: Asking detailed traffic question")
            print("=" * 70)
            try:
                result = await client.ask_traffic_question(
                    "请分析2023年12月曼德海峡发生异常的原因"
                )
                print("📄 Result:")
                print(result)
            except Exception as e:
                print(f"❌ Error: {e}")
            
            print("\n")
            
            # Test 4: Plot ship congestion
            print("=" * 70)
            print("TEST 4: Plotting ship congestion analysis")
            print("=" * 70)
            try:
                result = await client.plot_ship_congestion_analysis(
                    run_date="2023-12-31",
                    pipe_name="曼德海峡"
                )
                print("📄 Result:")
                print(result)
            except Exception as e:
                print(f"❌ Error: {e}")
        
        else:
            # Interactive mode
            print("📝 Interactive Mode - Examples:")
            print("  1. List tools")
            print("  2. Detect: 2023年12月 曼德海峡是否发生异常?")
            print("  3. Analyze: 请分析2023年12月曼德海峡发生异常的原因")
            print("  4. Plot: run_date=2023-12-31, pipe_name=曼德海峡")
            print("\nRun with --test flag to execute all tests\n")
            
            # Example: List tools
            print("=" * 70)
            print("Listing available tools...")
            print("=" * 70)
            try:
                tools = await client.list_tools()
                if "result" in tools and "tools" in tools["result"]:
                    print(f"\n✅ Found {len(tools['result']['tools'])} tools:")
                    for tool in tools["result"]["tools"]:
                        print(f"  - {tool.get('name', 'unknown')}")
                        if "description" in tool:
                            desc = tool["description"].split("\n")[0]
                            print(f"    {desc[:80]}...")
                else:
                    print(json.dumps(tools, indent=2, ensure_ascii=False))
            except Exception as e:
                print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
