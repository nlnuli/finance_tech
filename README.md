# Finance Tech

一个最小可运行的 FastAPI + Vite React TypeScript 项目。

## 目录结构

```text
backend/   FastAPI 后端
frontend/  React 前端
```

## 首次安装

在项目根目录执行：

```bash
cd /Users/yewen/finance_helpers/finance_tech
```

安装后端依赖：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

安装前端依赖：

```bash
cd frontend
npm install
```

## 启动后端

打开一个终端：

```bash
cd /Users/yewen/finance_helpers/finance_tech/backend
../.venv/bin/uvicorn app.main:app --reload
```

后端地址：

```text
http://127.0.0.1:8000
```

说明：

- 后端现在依赖 MCP 官方 SDK 和 `langchain-mcp-adapters`，需要 Python 3.10+
- 默认会自动启动一个本地 MCP server，把 `rag_search`、`calculator`、`current_time` 暴露给 agent
- 外部 MCP server 可通过 `backend/mcp_servers.json` 或环境变量 `MCP_CONFIG_PATH` 指向的 JSON 文件配置

示例：

```json
{
  "servers": [
    {
      "name": "weather",
      "transport": "http",
      "enabled": true,
      "url": "http://127.0.0.1:9000/mcp"
    }
  ]
}
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

预期返回：

```json
{"status":"ok"}
```

## 启动前端

再打开一个终端：

```bash
cd /Users/yewen/finance_helpers/finance_tech/frontend
npm run dev
```

前端地址：

```text
http://127.0.0.1:5173/
```

## 日常启动

后端：

```bash
cd /Users/yewen/finance_helpers/finance_tech/backend
../.venv/bin/uvicorn app.main:app --reload
```

前端：

```bash
cd /Users/yewen/finance_helpers/finance_tech/frontend
npm run dev
```

## 构建前端

```bash
cd /Users/yewen/finance_helpers/finance_tech/frontend
npm run build
```

## 常见问题

如果后端启动时报端口占用：

```text
ERROR: [Errno 48] Address already in use
```

查看占用 8000 端口的进程：

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
```

停止对应进程：

```bash
kill <PID>
```

或者换端口启动：

```bash
cd /Users/yewen/finance_helpers/finance_tech/backend
../.venv/bin/uvicorn app.main:app --reload --port 8001
```

如果前端无法请求后端，先确认后端 `/health` 可以访问，并确认 `frontend/.env` 或默认配置中的后端地址是：

```text
http://127.0.0.1:8000
```
