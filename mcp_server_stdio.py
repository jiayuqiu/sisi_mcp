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
from pathlib import Path
import json

from mcp_conductor.entry.main_traffic_detect import trigger_traffic_detect
from mcp_conductor.detector.pipe_detect_engine import pipe_detect_engine
from mcp_conductor.detector.plot_ship_congestion import plot_ship_congestion

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
      "请问，2023年12月 曼德海峡 是否发生异常？" -> ("2023-12-31", "曼德海峡")
      "请问，2023年4月 马六甲海峡 是否发生异常？" -> ("2023-04-30", "马六甲海峡")
    
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
            candidate = re.split(r"是否|会不会|有无|发生|异常|堵塞", candidate)[0].strip()
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
                "检测指定日期和通道是否发生交通异常。用于回答'是否异常'、'有没有异常'等简单检测问题。支持'马六甲海峡'和'曼德海峡'。\n"
                "Detects whether traffic congestion occurred for a specified date and shipping channel. Use for simple yes/no congestion detection questions.\n"
                "示例 / Example: 2023年12月 曼德海峡是否发生异常? / Was there congestion in the Mandeb Strait in December 2023?"
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
        ),
        Tool(
            name="ask_traffic_question",
            description=(
                "用自然语言提问交通异常原因分析问题。当问题包含'原因'、'为什么'、'分析'等关键词时使用此工具。系统将进行深度分析，结合天气、新闻等信息给出详细解释。\n"
                "Ask about traffic congestion causes and detailed analysis in natural language (Chinese). Use this tool when the question contains keywords like '原因' (reason), '为什么' (why), '分析' (analyze). The system will provide in-depth analysis combining weather, news, and other information.\n"
                "示例 / Example: 请分析 2023年12月 曼德海峡发生异常的原因。 / Please analyze the reason why the congestion happened in Mandeb Strait in December 2023."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "用中文提出的问题，包含年月、通道名称和分析请求 / Question in Chinese containing year, month, channel name, and analysis request"
                    }
                },
                "required": ["question"]
            }
        ),
        Tool(
            name="plot_ship_congestion_analysis",
            description=(
                "读取通道数据，检测变化点，并绘制船舶数量的折线图，标出异常区域。\n\n"
                "Reads pipe data, detects changepoints, and plots a line chart of ship counts, highlighting congestion areas."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "run_date": {
                        "type": "string",
                        "description": "分析窗口的结束日期 / End date for the analysis window (YYYY-MM-DD)",
                        "pattern": r"^\d{4}-\d{2}-\d{2}$"
                    },
                    "pipe_name": {
                        "type": "string",
                        "description": "要分析的通道名称 / Name of the channel to analyze",
                        "enum": ["马六甲海峡", "曼德海峡", "马六甲"]
                    }
                },
                "required": ["run_date", "pipe_name"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls for traffic detection."""
    
    if name == "detect_traffic_congestion":
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
                    f"示例：'请问，2023年12月 曼德海峡 是否发生异常？'"
                )
            )]

        # step 1: run changepoints detecting
        loop = asyncio.get_event_loop()
        changepoints_result = await loop.run_in_executor(
            None,
            pipe_detect_engine,
            run_date,
            pipe_name
        )

        if len(changepoints_result) > 0:
            changepoint_rsps = f"🚢 检测结果 / Detection Result\n 发生异常天数 {changepoints_result[pipe_name].shape[0]}"
            return [TextContent(type="text", text=changepoint_rsps)]
        else:
            return [TextContent(type="text", text=f"{run_date} {pipe_name} 无异常发生")]

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
                    f"示例：'请问，2023年12月 曼德海峡 异常原因'"
                )
            )]

        try:
            loop = asyncio.get_event_loop()
            response_parts = []

            # Step 2: Run congestion detection
            detect_result = await loop.run_in_executor(
                None,
                trigger_traffic_detect,
                run_date,
                pipe_name
            )

            # Prepare response parts
            response_parts = [
                f"## 💬 问题 / Question\n\n",
                f"{question}\n\n",
                f"---\n\n",
                f"## 📊 解析信息 / Parsed Information\n\n",
                f"- **📅 日期 / Date**: {run_date}\n",
                f"- **🌊 通道 / Channel**: {pipe_name}\n\n",
                f"---\n\n",
                f"## 🚢 检测结果 / Detection Result\n\n",
                f"{detect_result}\n"
            ]

            # json.dumps(result, ensure_ascii=False)
            return [TextContent(type="text", text="".join(response_parts))]

        except Exception as e:
            import traceback
            error_msg = (
                f"❌ 检测失败 / Detection Failed\n"
                f"问题 / Question: {question}\n"
                f"错误 / Error: {str(e)}\n\n"
                f"详细信息 / Details:\n{traceback.format_exc()}"
            )
            return [TextContent(type="text", text=error_msg)]

    if name == "plot_ship_congestion_analysis":
        run_date = arguments.get("run_date")
        pipe_name = arguments.get("pipe_name")

        if not run_date or not pipe_name:
            return [TextContent(
                type="text",
                text="错误：缺少必需参数 run_date 或 pipe_name / Error: Missing required parameters run_date or pipe_name"
            )]

        try:
            # Ensure output directory exists (relative to repo root)
            output_dir = "./tmp/images"
            loop = asyncio.get_event_loop()
            image_path = await loop.run_in_executor(
                None,
                plot_ship_congestion,
                run_date,
                pipe_name,
                3,  # month default
                0,  # day default
                output_dir
            )

            response = (
                f"🖼️ 船舶异常分析图 / Ship Congestion Plot\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📅 分析结束日期 / End Date: {run_date}\n"
                f"🌊 通道 / Channel: {pipe_name}\n"
                f"📁 图片路径 / Image: {image_path}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            )

            return [TextContent(type="text", text=response)]

        except Exception as e:
            import traceback
            error_msg = (
                f"❌ 绘图失败 / Plotting Failed\n"
                f"错误 / Error: {str(e)}\n\n"
                f"详细信息 / Details:\n{traceback.format_exc()}"
            )
            return [TextContent(type="text", text=error_msg)]

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
