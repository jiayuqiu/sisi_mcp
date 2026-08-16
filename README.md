# sisimcp — 航运交通异常检测平台

> Version 0.1.0

sisimcp 是一个面向海峡、运河和港口的航运交通检测平台。它同步船舶数量与
平均通行/停泊时长，使用日期生效的滚动百分位参数分别检测两个指标，并将方向
组合为可解释的交通状态。项目同时提供 MCP 服务、Dify 集成 API、Dify Chatflow
和 Next.js 可视化界面。

sisimcp detects shipping traffic anomalies across channels, canals, and ports. It
scores vessel count and average duration independently, then combines their directions
into an explainable traffic regime.

详细部署教程请参阅 [快速开始](docs/quick-start.md)。英文说明见
[README.en.md](README.en.md)。

## 主要功能 / Highlights

- **双指标检测**：同时检测 `ship_cnt`（船舶数量）和 `duration`（平均时长）。
- **日期生效参数**：按地点、指标和生效日期保存拟合参数，避免历史检测使用未来数据。
- **方向输出**：异常标记区分 `LOW`、`HIGH`、`MIXED`、`NORMAL` 和 `UNKNOWN`。
- **组合状态**：将数量与时长方向组合为 `CONGESTION`、`BLOCKAGE`、
  `AVOIDANCE`、`HIGH_THROUGHPUT`、`DELAY` 等状态。
- **实时监控**：按地点、指标和方向跟踪异常率，并识别阈值偏移。
- **可重复回建**：按日执行 D-1 拟合和 D 日检测，支持 SQLite 备份和 dry run。
- **Dify 集成**：提供异常检测、原因分析、工作日志以及工作流部署工具。
- **可视化**：在同一图表显示船舶数量、平均时长、方向异常和组合状态。

## 架构 / Architecture

| 组件 | 路径 | 说明 |
|---|---|---|
| MCP HTTP Server | `mcp_conductor/servers/mcp_server_http.py` | FastMCP streamable HTTP 服务，转发 Dify Chatflow |
| Dify API Server | `mcp_conductor/servers/dify_api_server.py` | 检测、分析和工作日志 API |
| Detection Engine | `mcp_conductor/detector/` | 滚动百分位拟合、检测、状态分类和监控 |
| Pipeline Entries | `mcp_conductor/entry/` | 数据同步、建表、拟合、检测、回建和 Dify 部署 CLI |
| Frontend | `frontend_nextjs/` | Chatbot、工作流日志和数量/时长图表 |
| Database | `data/sisi.sqlite` | 观测数据、参数版本、检测结果和监控快照 |
| Dify Resources | `mcp_conductor/resources/dify/` | Chatflow DSL 与自定义工具 OpenAPI 定义 |

## 快速启动 / Quick Start

### 1. 环境要求

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Node.js（仅本地运行前端时需要）
- Docker 与 Docker Compose（推荐）
- 已运行且 Docker 网络名为 `sisi-dify-platform_default` 的 Dify 实例

### 2. 安装依赖

```bash
uv sync
```

### 3. 配置环境变量

在仓库根目录创建 `.env`，根据使用场景设置以下变量：

```dotenv
# BCI 数据同步
BCI_BASE_URL=
BCI_APP_ID=
BCI_SECRET_KEY=
BCI_SYNC_START_DATE=2026-01-01

# AI 分析
DEEPSEEK_API_KEY=
SISI_API_KEY=

# Dify 应用调用
DIFY_CHATFLOW_URL=http://localhost/v1
DIFY_API_KEY=

# 可选：自动部署 Dify 工作流
DIFY_CONSOLE_API_URL=http://localhost:7080/console/api
DIFY_ADMIN_API_KEY=
DIFY_WORKSPACE_ID=
DIFY_APP_ID=
```

不要提交包含真实密钥的 `.env` 文件。

### 4. 启动服务

```bash
cd docker
docker compose up -d --build
docker compose ps
```

默认端口：

| 服务 | 地址 |
|---|---|
| Next.js frontend | `http://localhost:3001` |
| Dify integration API | `http://localhost:8002` |
| MCP streamable HTTP | `http://localhost:8010` |

## 数据与检测工作流 / Detection Workflow

首次运行时创建或升级 SQLite schema：

```bash
uv run python -m mcp_conductor.entry.main_setup_schema
```

同步 BCI 数据：

```bash
uv run python -m mcp_conductor.entry.main_sync_bci_data \
  --start-date 2026-01-01 --end-date 2026-08-01
```

先预览、再保存滚动百分位参数：

```bash
uv run python -m mcp_conductor.entry.main_fit_model --dry_run
uv run python -m mcp_conductor.entry.main_fit_model
```

运行指定日期的检测。检测结果保存后会自动刷新监控快照：

```bash
uv run python -m mcp_conductor.entry.main_traffic_detect \
  --run_date 2026-08-01
```

单独查看或保存监控快照：

```bash
uv run python -m mcp_conductor.entry.main_monitor_roll_percentile --dry_run
uv run python -m mcp_conductor.entry.main_monitor_roll_percentile
```

按时间顺序回建历史结果，确保每个检测日只使用截至前一天的数据：

```bash
uv run python -m mcp_conductor.entry.main_rebuild_detection \
  --start-date 2026-05-01 --end-date 2026-08-01 --dry-run

uv run python -m mcp_conductor.entry.main_rebuild_detection \
  --start-date 2026-05-01 --end-date 2026-08-01
```

非 dry-run 回建会先在 `data/backups/` 创建 SQLite 备份。

## 检测结果 / Detection Output

每个地点的结果包含两条检测通道：

| 字段 | 含义 |
|---|---|
| `anomaly_flag` / `direction` | 船舶数量异常标记与方向 |
| `ratio_low` / `ratio_high` | 数量窗口中低于/高于阈值的比例 |
| `duration_anomaly_flag` / `duration_direction` | 平均时长异常标记与方向 |
| `duration_ratio_low` / `duration_ratio_high` | 时长窗口中低于/高于阈值的比例 |
| `duration_status` | 时长通道是否有可用数据与参数 |
| `regime` | 数量与时长组合后的交通状态 |

示例状态：

| 数量方向 | 时长方向 | 状态 |
|---|---|---|
| `HIGH` | `HIGH` | `CONGESTION` |
| `LOW` | `HIGH` | `BLOCKAGE` |
| `LOW` | `LOW` | `AVOIDANCE` |
| `HIGH` | `LOW` | `HIGH_THROUGHPUT` |
| `NORMAL` | `HIGH` | `DELAY` |

## Dify 工作流部署 / Dify Deployment

部署命令默认只做本地文件和远端目标的只读预检：

```bash
uv run python -m mcp_conductor.entry.main_deploy_dify_workflow \
  --workspace-id "$DIFY_WORKSPACE_ID" \
  --app-id "$DIFY_APP_ID"
```

确认后更新草稿，或更新并发布：

```bash
uv run python -m mcp_conductor.entry.main_deploy_dify_workflow \
  --workspace-id "$DIFY_WORKSPACE_ID" \
  --app-id "$DIFY_APP_ID" \
  --apply

uv run python -m mcp_conductor.entry.main_deploy_dify_workflow \
  --workspace-id "$DIFY_WORKSPACE_ID" \
  --app-id "$DIFY_APP_ID" \
  --apply --publish
```

CLI 会在写入前备份现有 Dify 配置。更多说明见
[`mcp_conductor/resources/dify/README.md`](mcp_conductor/resources/dify/README.md)。

## 前端开发 / Frontend Development

```bash
cd frontend_nextjs
npm install
npm run dev
```

本地开发地址为 `http://localhost:3000`。生产构建检查：

```bash
npm run build
```

## 测试 / Testing

只对项目自身的测试目录运行 pytest：

```bash
uv run pytest -q tests/
```

不要在仓库根目录直接运行不带路径的 `pytest`；它也会收集 `dify/` 子模块的
大型测试套件，而该套件使用独立的依赖和运行环境。DeepSeek、SISI 和 BCI 的在线
集成测试还需要相应的 API 密钥与网络访问。

## 生产部署 / Production Deployment

`pipelines/deploy_prod.sh` 提供 Ubuntu/Debian 主机的受控部署流程，包括：

- 校验目标提交是否为当前生产版本的 fast-forward；
- 构建镜像、备份 SQLite、升级 schema 并拟合参数；
- 重建应用容器并检查健康状态；
- 可选同步 BCI 历史数据和部署 Dify 工作流。

查看完整参数：

```bash
bash pipelines/deploy_prod.sh --help
```

## 贡献 / Contributing

1. 从 `develop` 创建功能分支。
2. 提交聚焦且带测试的更改。
3. 运行 `uv run pytest -q tests/` 和 `npm run build`。
4. 推送分支并提交合并请求。

## License

请参阅仓库中的许可文件；若未提供许可文件，请在复用或分发前联系维护者。
