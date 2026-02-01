# 如何使用 MCP Server 分析曼德海峡拥堵情况
# How to Use MCP Server to Analyze Mandeb Strait Congestion

## ✅ 配置已完成 / Configuration Complete

你的 MCP Server 已经配置完成！以下是如何使用它的详细说明。

Your MCP Server is already configured! Here's how to use it.

---

## 📋 前提条件检查 / Prerequisites Check

✅ **已配置项 / Already Configured:**
- VS Code 设置文件已配置 MCP Server (`.vscode/settings.json`)
- Python 虚拟环境已激活 (Python 3.11.14)
- 所有必需的依赖包已安装 (mcp, pandas, ruptures, etc.)

---

## 🚀 使用方法 / Usage Methods

### 方法 1：在 GitHub Copilot Chat 中直接提问（推荐）
### Method 1: Ask Directly in GitHub Copilot Chat (Recommended)

这是最简单的方法！只需：

1. **打开 Copilot Chat**（点击侧边栏的 Copilot 图标或按 `Ctrl+Shift+I`）

2. **直接用中文提问**，例如：

```
请问，xxxx年xx月 xx海峡 是否发生拥堵？

请问，xxxx年xx月 马六甲海峡 是否发生拥堵？

检测 yyyy-mm-dd aaa海峡的交通情况

yyy年mm月aaa海峡有拥堵吗？
```

3. **Copilot 会自动：**
   - 识别你的问题
   - 调用 MCP Server 的工具
   - 运行拥堵检测
   - 返回分析结果

#### 📊 返回的信息包括：
- ✅ 是否发生拥堵（Yes/No）
- 📈 变点检测结果
- 🌤️ 天气信息（如果可用）
- 📰 相关新闻（如果可用）
- 📊 船舶数量趋势

---

### 方法 2：使用 @-mention 明确调用 MCP 工具
### Method 2: Use @-mention to Explicitly Call MCP Tools

在 Copilot Chat 中，你可以使用 `@workspace` 来访问 MCP 工具：

```
@workspace 检测 2023-04-30 曼德海峡 的交通拥堵情况

@workspace 请使用 detect_traffic_congestion 工具分析曼德海峡在2023年4月的拥堵情况
```

---

### 方法 3：直接运行 MCP Server（测试用）
### Method 3: Run MCP Server Directly (For Testing)

如果你想测试 MCP Server 是否正常工作，可以直接运行：

```bash
/home/jerry/codebase/sisimcp/.venv/bin/python mcp_server.py
```

**注意：** 这个命令会启动服务器，但它通过 stdio 通信，主要用于调试。正常使用时，VS Code 会自动管理 MCP Server 的生命周期。

---

### 方法 4：使用原始检测脚本（不通过 MCP）
### Method 4: Use Original Detection Script (Without MCP)

如果你想直接运行检测而不使用 MCP Server：

```bash
/home/jerry/codebase/sisimcp/.venv/bin/python -m mcp_conductor.entry.main_traffic_detect --run_date 2023-04-30 --pipe 曼德海峡
```

---

## 🎯 MCP Server 提供的工具 / Available MCP Tools

你的 MCP Server 暴露了两个工具：

### 1️⃣ `detect_traffic_congestion`
直接检测指定日期和通道的拥堵情况

**参数：**
- `run_date`: 日期（YYYY-MM-DD 格式，通常是月末）
- `pipe_name`: 通道名称（"曼德海峡" 或 "马六甲海峡"）

**示例：**
```json
{
  "run_date": "2023-04-30",
  "pipe_name": "曼德海峡"
}
```

### 2️⃣ `ask_traffic_question`
用自然语言提问，自动解析日期和通道

**参数：**
- `question`: 中文问题

**示例：**
```
"请问，2023年4月 曼德海峡 是否发生拥堵？"
```

---

## 💡 使用提示 / Tips

### ✅ DO（推荐做法）：
- ✅ 在问题中明确包含年份、月份和通道名称
- ✅ 使用通道的完整名称："曼德海峡" 或 "马六甲海峡"
- ✅ 日期使用月末（如 4月30日、12月31日）
- ✅ 直接在 Copilot Chat 中提问，让它自动调用工具

### ❌ DON'T（避免）：
- ❌ 不要忘记重启 VS Code（修改 MCP 配置后）
- ❌ 不要使用不完整的日期（只说"4月"而不说年份）
- ❌ 不要使用简写通道名（除非是"马六甲"）

---

## 🔍 故障排除 / Troubleshooting

### 问题 1：Copilot 没有调用 MCP 工具
**解决方案：**
1. 确保 VS Code 已重启
2. 检查 `.vscode/settings.json` 中的 MCP 配置
3. 尝试在问题中更明确地提到"检测"或"分析"

### 问题 2：找不到数据文件
**解决方案：**
- 确保 `data/pipe/` 目录中有对应日期的 CSV 文件
- 对于测试，可以使用 `data/dummy/` 中的示例数据

### 问题 3：Python 环境问题
**解决方案：**
```bash
# 激活虚拟环境
source /home/jerry/codebase/sisimcp/.venv/bin/activate

# 重新安装依赖
pip install -r requirements.txt
```

---

## 📚 示例对话 / Example Conversations

### 示例 1：简单提问
**你：** 请问，2023年4月 曼德海峡 是否发生拥堵？

**Copilot：** *(调用 MCP 工具，返回分析结果)*
```
🚢 交通拥堵检测结果
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 日期: 2023-04-30
🌊 通道: 曼德海峡
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[检测结果详情...]
```

### 示例 2：比较分析
**你：** 比较 2023年4月 曼德海峡 和 马六甲海峡 的拥堵情况

**Copilot：** *(自动调用两次 MCP 工具，分别检测两个海峡，然后比较结果)*

### 示例 3：趋势分析
**你：** 2023年4月到6月期间，曼德海峡的拥堵情况如何？

**Copilot：** *(调用多次 MCP 工具，分别检测 4月、5月、6月，然后总结趋势)*

---

## 🎉 快速开始 / Quick Start

1. **打开 VS Code** 并加载此工作区
2. **打开 Copilot Chat**（侧边栏或 `Ctrl+Shift+I`）
3. **输入问题：** `请问，2023年4月 曼德海峡 是否发生拥堵？`
4. **查看结果！** 🎊

---

## 📞 获取帮助 / Get Help

如果遇到问题，可以：
- 查看 `README.md` 了解更多架构信息
- 检查 `mcp_server.py` 的日志输出
- 运行测试：`pytest tests/`

---

**祝你使用愉快！Happy analyzing! 🚢📊**
