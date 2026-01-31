# Dify Integration Guide for MCP Traffic Detection Server

This guide provides step-by-step instructions to integrate your MCP traffic detection server with Dify.

## Quick Start

### 1. Start the Servers

```bash
# Make the setup script executable
chmod +x setup_dify_integration.sh

# Run the setup script
./setup_dify_integration.sh
```

This will start:
- MCP Server on port 8000
- Dify Wrapper API on port 8001

### 2. Test the Integration

```bash
# Make the test script executable
chmod +x test_dify_integration.sh

# Run the test
./test_dify_integration.sh
```

---

## Detailed Configuration in Dify

### Access Dify's Tool Management

1. **Login to Dify**
   - Open your browser and navigate to your Dify instance (e.g., `http://localhost` or `https://your-dify-domain.com`)
   - Login with your credentials

2. **Navigate to Tools Section**
   - Click **"Studio"** in the top navigation bar
   - Click **"Tools"** in the left sidebar
   - You should see a page titled "Tools" with options to create or import tools

### Add Tool 1: Detect Traffic Congestion

1. **Click "Create Custom Tool" Button**
   - Look for a button that says "Create Tool", "Add Tool", or "Create Custom Tool"
   - Click it to open the tool creation form

2. **Fill in Basic Information**
   ```
   Tool Name: detect_traffic_congestion
   Label/Display Name: 检测交通异常 (Detect Traffic Congestion)
   Description: 检测指定日期和通道是否发生交通异常。支持马六甲海峡和曼德海峡。
   Category: Data Analysis (or leave default)
   ```

3. **Configure API Settings**

   **Authentication:**
   - Select: `No Auth` or `None`

   **HTTP Method:**
   - Select: `POST`

   **Request URL:**
   ```
   # If Dify is running locally (not in Docker):
   http://localhost:8001/api/detect_congestion

   # If Dify is running in Docker:
   http://host.docker.internal:8001/api/detect_congestion
   ```

   **Headers:**
   - Add header: `Content-Type: application/json`

   **Request Body Type:**
   - Select: `JSON` or `application/json`

   **Request Body Template:**
   ```json
   {
     "question": "{{question}}"
   }
   ```

4. **Define Input Parameters**

   Click "Add Parameter" or similar button, then fill:
   ```
   Parameter Name: question
   Display Name: 问题
   Type: String / Text
   Required: Yes ✓
   Description: 请输入包含年月和通道名称的问题，例如：2023年12月 曼德海峡是否发生异常？
   Default Value: (leave empty)
   ```

5. **Configure Output**
   ```
   Response Type: JSON
   Extract Path: (leave default or specify if needed)
   Output Variable Name: result
   ```

6. **Test the Tool**
   - Look for a "Test" button
   - Enter a test question: `2023年12月 曼德海峡是否发生异常？`
   - Click "Run Test" or "Test"
   - You should see a response with detection results

7. **Save the Tool**
   - Click "Save" or "Create" button
   - The tool is now available in your tool library

### Add Tool 2: Ask Traffic Question

Repeat the same process with these values:

```
Tool Name: ask_traffic_question
Display Name: 分析交通异常原因 (Analyze Traffic Congestion)
Description: 深度分析交通异常原因，提供详细解释和数据支持
URL: http://localhost:8001/api/ask_question
   (or http://host.docker.internal:8001/api/ask_question for Docker)
Method: POST
Body: {"question": "{{question}}"}

Parameter:
  - name: question
  - type: String
  - required: Yes
  - description: 请输入需要分析的问题，例如：请分析2023年12月曼德海峡发生异常的原因
```

Test with: `请分析2023年12月曼德海峡发生异常的原因`

### Add Tool 3: Plot Ship Congestion

```
Tool Name: plot_ship_congestion_analysis
Display Name: 绘制船舶拥堵分析图 (Plot Ship Congestion)
Description: 绘制船舶数量折线图，标注异常时段
URL: http://localhost:8001/api/plot_analysis
   (or http://host.docker.internal:8001/api/plot_analysis for Docker)
Method: POST
Body: {"run_date": "{{run_date}}", "pipe_name": "{{pipe_name}}"}

Parameters:
  1. run_date
     - type: String
     - required: Yes
     - description: 分析结束日期，格式：YYYY-MM-DD，例如：2023-12-31

  2. pipe_name
     - type: String
     - required: Yes
     - description: 通道名称，可选：马六甲海峡、曼德海峡、马六甲
```

Test with:
- run_date: `2023-12-31`
- pipe_name: `曼德海峡`

---

## Using Tools in Dify Applications

### Option A: Create an Agent Application

1. **Create New App**
   - Go to Studio → Click "Create App"
   - Select "Agent" or "Chatbot"
   - Give it a name: "交通异常检测助手" (Traffic Detection Assistant)

2. **Configure the Agent**

   **System Prompt:**
   ```
   你是一个海运交通异常检测助手。你可以帮助用户：

   1. 检测某个时间段的交通是否异常（使用 detect_traffic_congestion 工具）
   2. 分析交通异常的原因（使用 ask_traffic_question 工具）
   3. 生成船舶拥堵分析图表（使用 plot_ship_congestion_analysis 工具）

   支持的通道：
   - 马六甲海峡
   - 曼德海峡

   当用户询问时，请选择合适的工具进行分析。
   ```

3. **Add Tools to Agent**
   - Find the "Tools" section in the agent configuration
   - Click "Add Tool" or "Select Tools"
   - Check the boxes for:
     - ✓ detect_traffic_congestion
     - ✓ ask_traffic_question
     - ✓ plot_ship_congestion_analysis
   - Click "Confirm" or "Add"

4. **Configure Model Settings**
   - Select a model (e.g., GPT-4, Claude, or your preferred model)
   - Adjust temperature and other parameters as needed

5. **Publish the Agent**
   - Click "Publish" or "Deploy" button
   - Your agent is now ready to use!

### Option B: Create a Workflow Application

1. **Create Workflow**
   - Go to Studio → Create App → Workflow

2. **Add Tool Nodes**
   - Drag "Tool" node from the left panel
   - Configure it to use your custom tools
   - Connect nodes in your desired flow

3. **Example Workflow:**
   ```
   [Start] → [LLM: Parse User Question] → [Tool: detect_traffic_congestion]
   → [Condition: Has Congestion?]
      → Yes → [Tool: ask_traffic_question] → [Tool: plot_analysis] → [End]
      → No → [LLM: Generate Response] → [End]
   ```

---

## Testing Your Integration

### Test in Dify Chat Interface

Once your agent is published, try these queries:

**Test 1: Simple Detection**
```
用户: 请问，2023年12月 曼德海峡 是否发生异常？
预期: 系统调用 detect_traffic_congestion 工具并返回检测结果
```

**Test 2: Detailed Analysis**
```
用户: 请分析 2023年12月 曼德海峡发生异常的原因
预期: 系统调用 ask_traffic_question 工具并返回详细分析
```

**Test 3: Generate Chart**
```
用户: 请为 2023年12月 曼德海峡 生成船舶拥堵分析图
预期: 系统调用 plot_ship_congestion_analysis 工具并返回图片路径
```

**Test 4: Complex Query**
```
用户: 2023年12月马六甲海峡和曼德海峡分别的情况如何？
预期: 系统分别调用工具检测两个通道的情况
```

---

## Troubleshooting

### Problem 1: Dify Can't Connect to localhost

**Symptom:** Tools return connection errors like "Connection refused"

**Solution:**
- If Dify is running in Docker, it cannot access `localhost` on the host machine
- Change all tool URLs from `localhost` to `host.docker.internal`
- Example: `http://host.docker.internal:8001/api/detect_congestion`

**Alternative Solution:**
Add to your Dify docker-compose.yml:
```yaml
services:
  api:
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

### Problem 2: CORS Errors

**Symptom:** Browser console shows CORS policy errors

**Solution:**
- The dify_wrapper.py already includes CORS middleware
- If you need to restrict origins, edit dify_wrapper.py:
```python
allow_origins=["http://your-dify-domain.com"]
```

### Problem 3: MCP Server Crashes

**Symptom:** Tools return 500 errors or timeout

**Solution:**
1. Check MCP server logs:
   ```bash
   tail -f ./tmp/mcp_server.log
   ```

2. Restart the MCP server:
   ```bash
   pkill -f mcp_server_http.py
   python3 mcp_server_http.py
   ```

3. Check if required data files exist for your analysis

### Problem 4: Tools Not Appearing in Dify

**Symptom:** Can't find your custom tools when creating an agent

**Solution:**
1. Ensure tools are saved properly
2. Refresh the Dify page
3. Check if you're logged in with the correct account
4. Verify tool permissions (if using team/organization features)

### Problem 5: JSON Parsing Errors

**Symptom:** "Invalid JSON" or parsing errors

**Solution:**
- Ensure the request body template uses proper variable syntax: `{{variable_name}}`
- Check that all JSON is valid (use a JSON validator)
- Make sure parameter names match exactly (case-sensitive)

---

## Advanced Configuration

### Adding Authentication

If you want to secure your API:

1. **Modify dify_wrapper.py** to add API key authentication:
```python
from fastapi import Header, HTTPException

async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != "your-secret-key":
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return x_api_key

# Add dependency to endpoints
@app.post("/api/detect_congestion", dependencies=[Depends(verify_api_key)])
async def detect_congestion(request: QuestionRequest):
    # ... existing code
```

2. **In Dify tool configuration:**
   - Authentication Type: `API Key` or `Custom`
   - Header Name: `X-API-Key`
   - Header Value: `your-secret-key`

### Using Environment Variables

Create a `.env` file:
```env
MCP_HOST=0.0.0.0
MCP_PORT=8000
WRAPPER_HOST=0.0.0.0
WRAPPER_PORT=8001
API_KEY=your-secret-key
```

---

## Production Deployment

### Using Docker Compose

Create `docker-compose.yml`:
```yaml
version: '3.8'

services:
  mcp-server:
    build: .
    command: python mcp_server_http.py
    ports:
      - "8000:8000"
    volumes:
      - ./tmp:/app/tmp
    restart: unless-stopped

  dify-wrapper:
    build: .
    command: python dify_wrapper.py
    ports:
      - "8001:8001"
    depends_on:
      - mcp-server
    environment:
      - MCP_BASE_URL=http://mcp-server:8000
    restart: unless-stopped
```

Run with:
```bash
docker-compose up -d
```

---

## Summary

You now have three tools available in Dify:

| Tool | Purpose | Example Use |
|------|---------|-------------|
| `detect_traffic_congestion` | Quick yes/no detection | "2023年12月曼德海峡是否异常？" |
| `ask_traffic_question` | Detailed analysis | "请分析2023年12月曼德海峡异常原因" |
| `plot_ship_congestion_analysis` | Visual chart generation | "绘制2023年12月曼德海峡分析图" |

**Next Steps:**
1. Create an agent or workflow in Dify
2. Add the three tools to your application
3. Test with sample questions
4. Customize the system prompt for better results
5. Deploy to production if needed

For more help, check the logs or test individual endpoints with curl or Postman.
