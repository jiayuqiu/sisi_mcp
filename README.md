# sisimcp - Traffic Detection MCP Server

## 介绍 / Introduction

sisimcp 是一个用于检测海峡交通拥堵的 MCP (Model Context Protocol) 服务器。它可以分析船舶数量数据，结合天气和新闻信息，判断马六甲海峡和曼德海峡是否发生拥堵。

sisimcp is an MCP (Model Context Protocol) server for detecting traffic congestion in shipping channels. It analyzes vessel count data combined with weather and news information to determine if congestion has occurred in the Malacca Strait and Mandeb Strait.

## 架构 / Architecture

- **MCP Server**: `mcp_server.py` - 主要的 MCP 服务器，暴露两个工具供 Copilot 调用
- **Detection Engine**: `mcp_conductor/detector/` - 基于变点检测的拥堵分析引擎
- **AI Platforms**: `mcp_conductor/ai_platforms/` - 集成 DeepSeek 和 SISI-AI 进行网络搜索和文本处理
- **Data**: `data/pipe/` - 通道船舶数量数据（CSV 格式）

## 安装 / Installation

1. 安装依赖 / Install dependencies:
```bash
pip install -r requirements.txt
```

2. 配置环境变量 / Configure environment variables:
创建 `.env` 文件或设置必要的 API 密钥。

3. VS Code 配置 / VS Code Configuration:
MCP 服务器已在 `.vscode/settings.json` 中配置，VS Code Copilot 会自动发现并使用它。

## 使用方法 / Usage

### 方式 1：通过 Copilot 聊天调用 / Method 1: Call via Copilot Chat

启动 VS Code 后，MCP 服务器会自动加载。你可以在 Copilot 聊天中直接提问：

After starting VS Code, the MCP server will load automatically. You can ask questions directly in Copilot Chat:

**示例问题 / Example Questions:**

```
请问，2023年12月 曼德海峡 是否发生拥堵？

请问，2023年4月 马六甲海峡 是否发生拥堵？

检测 2023-12-31 曼德海峡的交通情况

Check traffic congestion in Malacca Strait on 2023-04-30
```

### 方式 2：直接运行 MCP 服务器 / Method 2: Run MCP Server Directly

```bash
python mcp_server.py
```

服务器将通过 stdio 与客户端通信 / The server will communicate with clients via stdio.

### 方式 3：使用原始检测脚本 / Method 3: Use Original Detection Script

```bash
python -m mcp_conductor.entry.main_traffic_detect --run_date 2023-12-31 --pipe 曼德海峡
```

### 方式 4：使用 Flask API（备用）/ Method 4: Use Flask API (Alternative)

```bash
python flask_server.py
```

访问 / Access:
- `http://localhost:5000/detect?run_date=2023-12-31&pipe=曼德海峡`
- `http://localhost:5000/run-queries` - 运行预定义查询

## MCP 工具 / MCP Tools

MCP 服务器提供两个工具 / The MCP server provides two tools:

### 1. `detect_traffic_congestion`

检测指定日期和通道的交通拥堵情况。

**参数 / Parameters:**
- `run_date` (string, required): 日期格式 YYYY-MM-DD / Date in format YYYY-MM-DD
- `pipe_name` (string, required): 通道名称 / Channel name
  - 可选值 / Options: `马六甲海峡`, `曼德海峡`, `马六甲`

**示例 / Example:**
```json
{
  "run_date": "2023-12-31",
  "pipe_name": "曼德海峡"
}
```

### 2. `ask_traffic_question`

使用自然语言提问交通拥堵情况，系统会自动解析日期和通道信息。

**参数 / Parameters:**
- `question` (string, required): 中文问题 / Question in Chinese

**示例 / Example:**
```json
{
  "question": "请问，2023年12月 曼德海峡 是否发生拥堵？"
}
```

## 数据格式 / Data Format

船舶数量数据文件应放在 `data/pipe/` 目录下，文件名格式：
`【集装箱】通道在港船舶数量YYYY-MM-DD.csv`

CSV 文件应包含以下列 / CSV files should contain:
- 日期 / Date
- 通道名称 / Channel name
- 船舶数量 / Vessel count

## 测试 / Testing

运行测试 / Run tests:
```bash
pytest tests/
```

## 支持的通道 / Supported Channels

- 马六甲海峡 / Malacca Strait
- 曼德海峡 / Mandeb Strait

## 技术栈 / Tech Stack

- **MCP (Model Context Protocol)**: 与 AI 助手（如 Copilot）集成
- **Python**: 主要编程语言
- **Pandas**: 数据处理
- **Ruptures**: 变点检测
- **DeepSeek API**: 网络搜索和问答
- **SISI-AI**: 文本总结和翻译
- **Flask**: 备用 HTTP API

## 配置 / Configuration

MCP 服务器配置位于 `.vscode/settings.json`:

```json
{
  "github.copilot.chat.mcp.servers": {
    "traffic-detection": {
      "command": "python",
      "args": ["${workspaceFolder}/mcp_server.py"],
      "enabled": true
    }
  }
}
```

## 贡献 / Contributing

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 许可 / License

请参阅项目许可文件。

## 联系 / Contact

如有问题，请开启 Issue。

---

**注意 / Note**: 确保在使用前配置好必要的 API 密钥和环境变量。/ Make sure to configure necessary API keys and environment variables before use.
