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

### Google Document AI

PDF 上传默认使用 Document AI OCR 和 Form Parser 并行解析。本地开发可使用 ADC：

```bash
gcloud auth application-default login
```

`backend/.env` 配置：

```env
DOCUMENT_AI_ENABLED=true
DOCUMENT_AI_PROJECT_ID=
DOCUMENT_AI_LOCATION=asia-southeast1
DOCUMENT_AI_OCR_PROCESSOR_ID=
DOCUMENT_AI_FORM_PROCESSOR_ID=
DOCUMENT_AI_PAGE_BATCH_SIZE=15
DOCUMENT_AI_BATCH_CONCURRENCY=2
DOCUMENT_AI_CALL_TIMEOUT_SECONDS=120
DOCUMENT_AI_TOTAL_TIMEOUT_SECONDS=600
DOCUMENT_AI_MAX_PAGES=200
DOCUMENT_AI_MAX_FILE_BYTES=
```

部署环境可通过工作负载身份或 `GOOGLE_APPLICATION_CREDENTIALS` 提供凭证。非 PDF 文件继续使用本地解析器。

跨页金融表格在 Form Parser 完成后使用本地确定性规则合并，不调用 LLM。默认只比较相邻页，并保留物理表、规则分数和行级页码来源：

```env
TABLE_STITCHING_ENABLED=true
TABLE_STITCHING_MIN_SCORE=0.75
```

审计结果保存在：

```text
backend/processed/{file_id}/table-stitching.json
```

将 `TABLE_STITCHING_ENABLED=false` 后重新上传或执行 reindex，可以恢复逐页表格 Chunking。

### Qdrant Hybrid Search

RAG 检索使用 OpenAI Dense Embedding 与 Qdrant 服务端 BM25，并由 Qdrant RRF 融合。Qdrant Cloud 集群需要先启用 Cloud Inference，并提供 `Qdrant/bm25` 模型。

```env
QDRANT_COLLECTION=finance_tech_chunks_hybrid_v1
QDRANT_CLOUD_INFERENCE=true
QDRANT_DENSE_VECTOR_NAME=dense
QDRANT_BM25_VECTOR_NAME=bm25
QDRANT_BM25_MODEL=Qdrant/bm25
QDRANT_BM25_LANGUAGE=none
QDRANT_BM25_TOKENIZER=multilingual
RAG_DENSE_CANDIDATE_COUNT=20
RAG_BM25_CANDIDATE_COUNT=20
RAG_FINAL_COUNT=4
```

将现有 ready 文件幂等重建到新 collection：

```bash
python scripts/reindex_qdrant_hybrid.py \
  --target-collection finance_tech_chunks_hybrid_v1
```

预览待处理文件，或恢复已经完成 Document AI 处理但索引失败的文件：

```bash
python scripts/reindex_qdrant_hybrid.py --dry-run
python scripts/reindex_qdrant_hybrid.py --include-recoverable-failed
```

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
