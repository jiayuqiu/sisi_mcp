# Dify Integration Guide

## Overview

This document provides the OpenAPI schemas needed to integrate the traffic detection tools into Dify.

## Important: Server URL Configuration

**When using Dify remotely or in Docker:**
- ❌ **DO NOT use** `http://localhost:8002`
- ✅ **USE your server's IP address** instead: `http://192.168.8.165:8002` (replace with your actual server IP)

**Why?**
- `localhost` only works when Dify and the API server are on the same machine
- When accessing Dify from another computer or when Dify runs in Docker, use the server's actual IP address
- Find your server IP with: `ip addr show` or `hostname -I`

## Server Setup

### Starting the Servers

```bash
./pipelines/start_mcp_server.sh
```

This will start:
- **MCP Server** on `http://0.0.0.0:8000` (for MCP protocol communication)
- **Dify API Server** on `http://0.0.0.0:8002` (REST API for Dify integration)

### Stopping the Servers

```bash
./pipelines/stop_mcp_server.sh
```

## Available Tools

The Dify API Server (`http://localhost:8002`) provides three endpoints:

1. `/api/detect_congestion` - Simple yes/no congestion detection
2. `/api/ask_question` - Detailed analysis with weather and news
3. `/api/plot_analysis` - Generate congestion visualization charts

## OpenAPI Schemas for Dify

### 1. Detect Traffic Congestion Tool

Use this schema in Dify's "Create Custom Tool" dialog:

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Detect Traffic Congestion",
    "description": "检测指定日期和通道是否发生交通异常",
    "version": "1.0.0"
  },
  "servers": [
    {
      "url": "http://YOUR_SERVER_IP:8002",
      "description": "Dify API Server (replace YOUR_SERVER_IP with actual IP like 192.168.8.165)"
    }
  ],
  "paths": {
    "/api/detect_congestion": {
      "post": {
        "summary": "检测交通异常",
        "description": "检测指定日期和通道是否发生交通异常。支持马六甲海峡和曼德海峡",
        "operationId": "detectCongestion",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "question": {
                    "type": "string",
                    "description": "用中文提出的问题，包含年月和通道名称",
                    "example": "2023年12月 曼德海峡是否发生异常？"
                  }
                },
                "required": ["question"]
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "检测结果",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "success": {
                      "type": "boolean"
                    },
                    "result": {
                      "type": "string"
                    },
                    "run_date": {
                      "type": "string"
                    },
                    "pipe_name": {
                      "type": "string"
                    },
                    "has_congestion": {
                      "type": "boolean"
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
```

### 2. Ask Traffic Question Tool

Use this schema for detailed analysis:

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Ask Traffic Question",
    "description": "分析交通异常原因，结合天气、新闻等信息",
    "version": "1.0.0"
  },
  "servers": [
    {
      "url": "http://YOUR_SERVER_IP:8002",
      "description": "Dify API Server (replace YOUR_SERVER_IP with actual IP like 192.168.8.165)"
    }
  ],
  "paths": {
    "/api/ask_question": {
      "post": {
        "summary": "分析交通异常原因",
        "description": "深度分析交通异常原因，结合天气、新闻等信息给出详细解释",
        "operationId": "askQuestion",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "question": {
                    "type": "string",
                    "description": "用中文提出的问题，包含年月、通道名称和分析请求",
                    "example": "请分析2023年12月曼德海峡发生异常的原因"
                  }
                },
                "required": ["question"]
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "详细分析结果",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "success": {
                      "type": "boolean"
                    },
                    "result": {
                      "type": "string",
                      "description": "Markdown格式的分析结果"
                    },
                    "run_date": {
                      "type": "string"
                    },
                    "pipe_name": {
                      "type": "string"
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
```

### 3. Plot Ship Congestion Tool

Use this schema for visualization:

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Plot Ship Congestion",
    "description": "绘制船舶异常分析图",
    "version": "1.0.0"
  },
  "servers": [
    {
      "url": "http://YOUR_SERVER_IP:8002",
      "description": "Dify API Server (replace YOUR_SERVER_IP with actual IP like 192.168.8.165)"
    }
  ],
  "paths": {
    "/api/plot_analysis": {
      "post": {
        "summary": "绘制船舶异常分析图",
        "description": "读取通道数据，检测变化点，并绘制船舶数量的折线图",
        "operationId": "plotAnalysis",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "run_date": {
                    "type": "string",
                    "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
                    "description": "分析窗口的结束日期，格式：YYYY-MM-DD",
                    "example": "2023-12-31"
                  },
                  "pipe_name": {
                    "type": "string",
                    "enum": ["马六甲海峡", "曼德海峡", "马六甲"],
                    "description": "要分析的通道名称",
                    "example": "曼德海峡"
                  }
                },
                "required": ["run_date", "pipe_name"]
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "图片路径和结果信息",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "success": {
                      "type": "boolean"
                    },
                    "result": {
                      "type": "string"
                    },
                    "image_path": {
                      "type": "string"
                    },
                    "run_date": {
                      "type": "string"
                    },
                    "pipe_name": {
                      "type": "string"
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
```

## Testing the API

### Test Congestion Detection

```bash
curl -X POST http://localhost:8002/api/detect_congestion \
  -H "Content-Type: application/json" \
  -d '{"question": "2023年12月 曼德海峡是否发生异常？"}'
```

Expected response:
```json
{
  "success": true,
  "result": "🚢 检测结果：2023-12-31 曼德海峡 发生异常，异常天数 31",
  "run_date": "2023-12-31",
  "pipe_name": "曼德海峡",
  "has_congestion": true
}
```

### Test Malacca Strait

```bash
curl -X POST http://localhost:8002/api/detect_congestion \
  -H "Content-Type: application/json" \
  -d '{"question": "2023年12月 马六甲海峡是否发生异常？"}'
```

Expected response:
```json
{
  "success": true,
  "result": "🚢 检测结果：2023-12-31 马六甲海峡 发生异常，异常天数 6",
  "run_date": "2023-12-31",
  "pipe_name": "马六甲海峡",
  "has_congestion": true
}
```

## Supported Shipping Channels

- 曼德海峡 (Mandeb Strait)
- 马六甲海峡 (Malacca Strait)
- 马六甲 (Malacca)

## Important Notes

1. **Server URL**: If Dify runs on a different machine, change `http://localhost:8002` to your actual server IP address
2. **Network Access**: Make sure port 8002 is accessible from your Dify instance
3. **Database**: Ensure `./data/sisi.sqlite` exists and contains the ship traffic data
4. **Virtual Environment**: The scripts automatically activate the `.venv` virtual environment if it exists

## Troubleshooting

### Servers won't start
- Check if dependencies are installed: `pip install -r requirements.txt`
- Check logs: `cat ./tmp/dify_api_server.log`

### Database errors
- Ensure `./data/sisi.sqlite` exists
- Check file permissions

### Connection errors from Dify
- Verify servers are running: `ps aux | grep -E '[d]ify_api_server|[m]cp_server_http'`
- **Check server URL**: If using Dify remotely, make sure you're using your server's IP address (e.g., `http://192.168.8.165:8002`), not `localhost`
- Find your server IP: `hostname -I | awk '{print $1}'` or `ip addr show`
- Test endpoints manually with curl from the Dify machine
- Check firewall settings: `sudo ufw allow 8002` (if using ufw)
- Verify network connectivity: `ping YOUR_SERVER_IP` from the Dify machine
