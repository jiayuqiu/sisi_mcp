#!/usr/bin/env python3
"""
Test HTTP API for Dify Integration (works without database)
Use this to test Dify integration before setting up the full database
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dify_test")

app = FastAPI(title="Dify Test API")

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


@app.post("/api/detect_anomaly")
async def detect_anomaly(request: QuestionRequest):
    """Test endpoint for congestion detection"""
    logger.info(f"Test detect_anomaly: {request.question}")

    return {
        "success": True,
        "result": f"🚢 测试响应：收到问题 '{request.question}'\n\n✅ 这是一个测试响应。实际功能需要配置数据库文件。\n\n检测逻辑将分析2023年12月的曼德海峡或马六甲海峡的交通数据。",
        "note": "This is a TEST response. Configure database for real analysis.",
        "question": request.question
    }


@app.post("/api/analyze_anomaly_reason")
async def analyze_anomaly_reason(request: QuestionRequest):
    """Test endpoint for detailed analysis"""
    logger.info(f"Test analyze_anomaly_reason: {request.question}")

    return {
        "success": True,
        "result": f"""## 💬 问题
{request.question}

---

## 📊 测试响应

这是一个测试端点。实际分析功能需要：
1. 配置 SQLite 数据库（data/sisi.sqlite）
2. 包含船舶交通数据
3. 天气和新闻数据（可选）

## 🚢 示例分析结果

实际功能将提供：
- 变化点检测分析
- 异常时段识别
- 天气影响分析
- 相关新闻事件

---

🔧 当前状态：测试模式
""",
        "note": "This is a TEST response. Configure database for real analysis.",
        "question": request.question
    }


@app.post("/api/plot_analysis")
async def plot_analysis(request: PlotRequest):
    """Test endpoint for plot generation"""
    logger.info(f"Test plot_analysis: {request.run_date}, {request.pipe_name}")

    return {
        "success": True,
        "result": f"""🖼️ 测试响应：绘图请求
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 日期: {request.run_date}
🌊 通道: {request.pipe_name}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ 测试模式：实际功能需要配置数据库

实际功能将生成包含以下内容的图表：
- 船舶数量时间序列
- 异常区域高亮显示
- 变化点标注
""",
        "note": "This is a TEST response. Configure database for real plotting.",
        "run_date": request.run_date,
        "pipe_name": request.pipe_name
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "mode": "TEST",
        "message": "Test server for Dify integration. Configure database for production use."
    }


@app.get("/")
async def root():
    return {
        "service": "Dify Test API",
        "mode": "TEST",
        "endpoints": [
            "/api/detect_anomaly",
            "/api/analyze_anomaly_reason",
            "/api/plot_analysis"
        ],
        "note": "This is a test server. Configure data/sisi.sqlite for production."
    }


if __name__ == "__main__":
    import uvicorn
    logger.info("🧪 Starting TEST server - configure database for production use")
    uvicorn.run(app, host="0.0.0.0", port=8003)
