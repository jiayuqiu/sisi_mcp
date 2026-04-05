#!/usr/bin/env python3
"""
Simple HTTP API for Dify Integration
Directly exposes the traffic detection functions as REST endpoints
"""
import os
import logging
import asyncio

# Configure logging early, before other imports create their loggers
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s"
)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import the actual tool functions
from mcp_conductor.entry.main_traffic_detect import pipe_traffic_detect
from mcp_conductor.detector.plot_ship_congestion import plot_ship_congestion
import re
import calendar
import sqlite3
from pathlib import Path
logger = logging.getLogger("dify_api")

app = FastAPI(title="Dify Traffic Detection API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QuestionRequest(BaseModel):
    question: str


class PlotRequest(BaseModel):
    run_date: str
    pipe_name: str


def parse_question(question: str) -> tuple[str | None, str | None]:
    """Parse a natural-language question to extract run_date and pipe name."""
    if not question:
        return None, None

    # Find year and month (optional day)
    ym_match = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月", question)
    if not ym_match:
        ym_match = re.search(r"(\d{4})[-/](\d{1,2})(?:[-/](\d{1,2}))?", question)

    run_date = None
    if ym_match:
        year = int(ym_match.group(1))
        month = int(ym_match.group(2))
        day = ym_match.group(3) if ym_match.lastindex and ym_match.lastindex >= 3 else None
        if day:
            run_date = f"{year:04d}-{month:02d}-{int(day):02d}"
        else:
            last_day = calendar.monthrange(year, month)[1]
            run_date = f"{year:04d}-{month:02d}-{last_day:02d}"

    # Extract pipe name
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


@app.get("/api/question_list")
async def question_list():
    """Return distinct pipe names as pre-built question suggestions."""
    try:
        db_path = Path("./data/sisi.sqlite")
        with sqlite3.connect(str(db_path)) as conn:
            rows = conn.execute("SELECT DISTINCT pipe_name FROM ship_cnt_in_pipe").fetchall()
        pipe_names = [r[0] for r in rows]
        question_list = [f"2024年1月 {name}是否拥堵" for name in pipe_names]
        return {"question_list": question_list}
    except Exception as e:
        logger.error("Error in question_list: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/detect_anomaly")
async def detect_anomaly(request: QuestionRequest):
    """Detect traffic congestion for specified date and channel"""
    try:
        logger.info(f"Detect anomaly request: {request.question}")

        # Parse the question
        run_date, pipe_name = parse_question(request.question)
        if not run_date or not pipe_name:
            return {
                "success": False,
                "message": "无法解析问题。请确保包含年月和通道名称。示例：2023年12月 曼德海峡是否发生异常？"
            }

        # Query pre-computed detection results from the view
        date_id = int(run_date.replace("-", ""))
        db_path = Path("./data/sisi.sqlite")
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT anomaly_flag, flag_name, description, quantile_10, quantile_90, anomaly_ratio "
                "FROM vw_m_pipe_anomaly_roll_percentile WHERE pipe_name = ? AND date_id = ?",
                (pipe_name, date_id),
            ).fetchone()

        if row is None:
            return {
                "success": False,
                "message": f"未找到 {run_date} {pipe_name} 的检测结果，请确认日期和通道名称是否正确。"
            }

        anomaly_flag, flag_name, description, quantile_10, quantile_90, anomaly_ratio = row
        is_anomaly = anomaly_flag == 1

        if is_anomaly:
            result_text = f"🚢 检测结果：{run_date} {pipe_name} 发生异常（{description}），近30日异常比率 {anomaly_ratio:.2%}"
        else:
            result_text = f"✅ 检测结果：{run_date} {pipe_name} 无异常发生（{description}），近30日异常比率 {anomaly_ratio:.2%}"

        logger.info(f"Detection result: {result_text}")
        return {
            "success": True,
            "result": result_text,
            "run_date": run_date,
            "pipe_name": pipe_name,
            "if_anomaly": is_anomaly,
            "anomaly_flag": anomaly_flag,
            "flag_name": flag_name,
            "quantile_10": quantile_10,
            "quantile_90": quantile_90,
            "anomaly_ratio": anomaly_ratio,
        }

    except Exception as e:
        logger.error(f"Error in detect_anomaly: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyze_anomaly_reason")
async def analyze_anomaly_reason(request: QuestionRequest):
    """Analyze traffic congestion with detailed information"""
    try:
        logger.info(f"Analyze anomaly reason request: {request.question}")

        # Parse the question
        run_date, pipe_name = parse_question(request.question)
        logger.info(f"analyze_anomaly_reason get {run_date} - {pipe_name}")
        if not run_date or not pipe_name:
            return {
                "success": False,
                "message": "无法解析问题。请确保包含年月和通道名称。示例：请分析2023年12月曼德海峡异常的原因"
            }

        # Run analysis in executor
        loop = asyncio.get_event_loop()
        analysis_result = await loop.run_in_executor(
            None,
            pipe_traffic_detect,
            run_date,
            pipe_name
        )

        result_text = f"""## 💬 问题
{request.question}

---

## 📊 解析信息
- **📅 日期**: {run_date}
- **🌊 通道**: {pipe_name}

---

## 🚢 分析结果
{analysis_result}
"""

        logger.info(f"Analysis completed for {run_date} {pipe_name}")
        return {
            "success": True,
            "result": result_text,
            "run_date": run_date,
            "pipe_name": pipe_name
        }

    except Exception as e:
        logger.error(f"Error in analyze_anomaly_reason: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/plot_analysis")
async def plot_analysis(request: PlotRequest):
    """Generate ship congestion plot"""
    try:
        logger.info(f"Plot analysis request: {request.run_date}, {request.pipe_name}")

        # Generate plot in executor
        output_dir = "./tmp/images"
        loop = asyncio.get_event_loop()
        image_path = await loop.run_in_executor(
            None,
            plot_ship_congestion,
            request.run_date,
            request.pipe_name,
            3,  # month default
            0,  # day default
            output_dir
        )

        result_text = f"""🖼️ 船舶异常分析图
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 分析结束日期: {request.run_date}
🌊 通道: {request.pipe_name}
📁 图片路径: {image_path}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

        logger.info(f"Plot generated: {image_path}")
        return {
            "success": True,
            "result": result_text,
            "image_path": image_path,
            "run_date": request.run_date,
            "pipe_name": request.pipe_name
        }

    except Exception as e:
        logger.error(f"Error in plot_analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Dify Traffic Detection API",
        "version": "1.0.0"
    }


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "service": "Dify Traffic Detection API",
        "endpoints": {
            "detect_anomaly": "/api/detect_anomaly",
            "analyze_anomaly_reason": "/api/analyze_anomaly_reason",
            "plot_analysis": "/api/plot_analysis",
            "health": "/health"
        },
        "status": "running"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
