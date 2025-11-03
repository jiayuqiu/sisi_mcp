# MCP HTTP Server for Traffic Detection

This server exposes traffic detection tools via HTTP using the `fastmcp` framework.

## Installation

```bash
pip install -r requirements.txt
```

## Running the Server

Start the HTTP server:

```bash
python mcp_server_http.py
```

The server will start on `http://localhost:8000` by default.

## Available Endpoints

### List All Tools
```bash
GET http://localhost:8000/tools
```

### 1. Detect Traffic Congestion
Detects whether traffic congestion occurred for a specified date and shipping channel.

```bash
POST http://localhost:8000/tools/detect_traffic_congestion
Content-Type: application/json

{
  "question": "2023年12月 曼德海峡是否发生异常?"
}
```

**Example with curl:**
```bash
curl -X POST http://localhost:8000/tools/detect_traffic_congestion \
  -H "Content-Type: application/json" \
  -d '{"question": "2023年12月 曼德海峡是否发生异常?"}'
```

### 2. Ask Traffic Question (Detailed Analysis)
Provides detailed analysis of traffic congestion causes, combining weather and news information.

```bash
POST http://localhost:8000/tools/ask_traffic_question
Content-Type: application/json

{
  "question": "请分析2023年12月曼德海峡发生异常的原因"
}
```

**Example with curl:**
```bash
curl -X POST http://localhost:8000/tools/ask_traffic_question \
  -H "Content-Type: application/json" \
  -d '{"question": "请分析2023年12月曼德海峡发生异常的原因"}'
```

### 3. Plot Ship Congestion Analysis
Generates a line chart showing ship counts with congestion periods highlighted.

```bash
POST http://localhost:8000/tools/plot_ship_congestion_analysis
Content-Type: application/json

{
  "run_date": "2023-12-31",
  "pipe_name": "曼德海峡"
}
```

**Example with curl:**
```bash
curl -X POST http://localhost:8000/tools/plot_ship_congestion_analysis \
  -H "Content-Type: application/json" \
  -d '{"run_date": "2023-12-31", "pipe_name": "曼德海峡"}'
```

## Testing

Run the test client to verify all endpoints:

```bash
python test_http_client.py
```

Make sure the server is running before executing the test client.

## Supported Channels

- 曼德海峡 (Mandeb Strait)
- 马六甲海峡 (Malacca Strait)
- 马六甲 (Malacca)

## Server Configuration

By default, the server runs on port 8000. To change the port, modify the last line in `mcp_server_http.py`:

```python
if __name__ == "__main__":
    mcp.run(port=YOUR_PORT)  # Change port here
```

## API Response Format

All endpoints return plain text responses containing:
- Detection results
- Analysis information
- Image paths (for plotting endpoint)
- Error messages (if applicable)

## Logs

Server logs are written to `./tmp/mcp_server.log`
