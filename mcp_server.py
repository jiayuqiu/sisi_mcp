#!/usr/bin/env python3
"""
MCP Server for Traffic Detection
Exposes traffic detection functionality as tools that can be called by AI assistants like Copilot.
"""
import logging
import asyncio
import re
import calendar
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from mcp_conductor.entry.main_traffic_detect import trigger_traffic_detect

# Configure logging to output to both file and stderr
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),  # stderr
        logging.FileHandler("./tmp/mcp_server.log", mode="a", encoding="utf-8")
    ]
)
logger = logging.getLogger("mcp_server")


# Create the MCP server instance
app = Server("traffic-detection-server")


def parse_question(question: str) -> tuple[str | None, str | None]:
    """Parse a natural-language question to extract a run_date (end of month) and pipe name.

    Examples handled:
      "请问，2023年12月 曼德海峡 是否发生拥堵？" -> ("2023-12-31", "曼德海峡")
      "请问，2023年4月 马六甲海峡 是否发生拥堵？" -> ("2023-04-30", "马六甲海峡")
    
    Args:
        question: Natural language question in Chinese
        
    Returns:
        Tuple of (run_date, pipe_name)
    """
    if not question:
        return None, None

    # Find year and month
    ym_match = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月", question)
    if not ym_match:
        ym_match = re.search(r"(\d{4})[-/](\d{1,2})", question)

    run_date = None
    if ym_match:
        year = int(ym_match.group(1))
        month = int(ym_match.group(2))
        # Get last day of month
        last_day = calendar.monthrange(year, month)[1]
        run_date = f"{year:04d}-{month:02d}-{last_day:02d}"

    # Try to extract pipe name: token after the month, before common question words
    pipe = None
    if ym_match:
        after = question[ym_match.end():]
        m = re.search(r"[:\s,，。]*(?P<name>[\u4e00-\u9fff\w\-\s]{2,20})", after)
        if m:
            candidate = m.group('name').strip()
            candidate = re.split(r"是否|会不会|有无|发生|拥堵|堵塞", candidate)[0].strip()
            if candidate:
                pipe = candidate

    # Fallback to known names
    known = ["曼德海峡", "马六甲海峡", "马六甲"]
    if not pipe:
        for k in known:
            if k in question:
                pipe = k
                break

    if pipe:
        pipe = pipe.strip()

    return run_date, pipe


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools for traffic detection."""
    return [
        Tool(
            name="detect_traffic_congestion",
            description=(
                "检测指定日期和通道的交通拥堵情况。支持马六甲海峡和曼德海峡的拥堵检测。"
                "通过分析船舶数量数据的变点，并结合天气和新闻信息，判断是否发生拥堵。\n\n"
                "Detect traffic congestion for a specific date and shipping channel. "
                "Supports Malacca Strait and Mandeb Strait congestion detection. "
                "Analyzes changepoints in vessel count data combined with weather and news information."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "run_date": {
                        "type": "string",
                        "description": "日期，格式为 YYYY-MM-DD（通常是月末日期）/ Date in YYYY-MM-DD format (typically end of month)",
                        "pattern": r"^\d{4}-\d{2}-\d{2}$"
                    },
                    "pipe_name": {
                        "type": "string",
                        "description": "通道名称，如'马六甲海峡'或'曼德海峡' / Channel name, e.g., '马六甲海峡' or '曼德海峡'",
                        "enum": ["马六甲海峡", "曼德海峡", "马六甲"]
                    }
                },
                "required": ["run_date", "pipe_name"]
            }
        ),
        Tool(
            name="ask_traffic_question",
            description=(
                "使用自然语言提问交通拥堵情况。系统会自动解析问题中的日期和通道信息。\n"
                "例如：'请问，2023年12月 曼德海峡 是否发生拥堵？'\n\n"
                "Ask about traffic congestion in natural language (Chinese). "
                "The system will automatically parse the date and channel from your question. "
                "Example: '请问，2023年12月 曼德海峡 是否发生拥堵？'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "用中文提出的问题，包含年月和通道名称 / Question in Chinese containing year, month, and channel name"
                    }
                },
                "required": ["question"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls for traffic detection."""
    
    if name == "detect_traffic_congestion":
        run_date = arguments.get("run_date")
        pipe_name = arguments.get("pipe_name")
        
        if not run_date or not pipe_name:
            return [TextContent(
                type="text",
                text="错误：缺少必需参数 run_date 或 pipe_name / Error: Missing required parameters run_date or pipe_name"
            )]
        
        try:
            # Run detection in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                trigger_traffic_detect,
                run_date,
                pipe_name
            )
            
            response = (
                f"🚢 交通拥堵检测结果 / Traffic Congestion Detection Result\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📅 日期 / Date: {run_date}\n"
                f"🌊 通道 / Channel: {pipe_name}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{result}"
            )
            
            return [TextContent(type="text", text=response)]
            
        except Exception as e:
            import traceback
            error_msg = (
                f"❌ 检测失败 / Detection Failed\n"
                f"错误 / Error: {str(e)}\n\n"
                f"详细信息 / Details:\n{traceback.format_exc()}"
            )
            return [TextContent(type="text", text=error_msg)]
    
    elif name == "ask_traffic_question":
        question = arguments.get("question")
        
        if not question:
            return [TextContent(
                type="text",
                text="错误：缺少问题参数 / Error: Missing question parameter"
            )]
        
        # Parse the question to extract date and pipe name
        run_date, pipe_name = parse_question(question)
        
        if not run_date or not pipe_name:
            return [TextContent(
                type="text",
                text=(
                    f"❓ 无法解析问题 / Unable to Parse Question\n\n"
                    f"您的问题：{question}\n\n"
                    f"请确保问题包含：\n"
                    f"1. 年份和月份（如：2023年12月）\n"
                    f"2. 通道名称（马六甲海峡 或 曼德海峡）\n\n"
                    f"示例：'请问，2023年12月 曼德海峡 是否发生拥堵？'"
                )
            )]
        
        try:
            # Run detection in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                trigger_traffic_detect,
                run_date,
                pipe_name
            )
            
            response = (
                f"💬 问题 / Question: {question}\n\n"
                f"🚢 检测结果 / Detection Result\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📅 解析日期 / Parsed Date: {run_date}\n"
                f"🌊 解析通道 / Parsed Channel: {pipe_name}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{result}"
            )
            
            return [TextContent(type="text", text=response)]
            
        except Exception as e:
            import traceback
            error_msg = (
                f"❌ 检测失败 / Detection Failed\n"
                f"问题 / Question: {question}\n"
                f"错误 / Error: {str(e)}\n\n"
                f"详细信息 / Details:\n{traceback.format_exc()}"
            )
            return [TextContent(type="text", text=error_msg)]
    
    else:
        return [TextContent(
            type="text",
            text=f"❌ 未知工具 / Unknown tool: {name}"
        )]


async def main():
    """Run the MCP server."""
    logger.info("✅ MCP server started successfully.")
    async with stdio_server() as (read_stream, write_stream):
        logger.info("MCP stdio server initialized.")
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
