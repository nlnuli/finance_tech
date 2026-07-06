# Finance Tech Docker Deployment

本文档说明如何将 Finance Tech 部署到一台 Linux 服务器。方案使用 Docker Compose 编排以下服务：

```text
Internet
  -> Caddy (HTTPS + React static files + reverse proxy)
      -> FastAPI backend
          -> MySQL
          -> Qdrant Cloud
          -> OpenAI API
          -> Google Document AI
          -> external MCP servers
```

## 1. 部署边界

容器内运行：

- React 前端与 Caddy。
- FastAPI、LangGraph、Memory 和本地 stdio MCP Server。
- MySQL 8.4。
- 一次性数据库初始化任务。

外部服务：

- Qdrant Managed Cloud。
- OpenAI 或兼容 API。
- Google Document AI。
- Tavily 等远程 MCP Server。

当前 Hybrid Search 使用 Qdrant 服务端 `Qdrant/bm25`，依赖 Cloud Inference，因此本方案不启动本地 Qdrant 容器。部署前需要在 Qdrant Cloud 控制台确认目标集群已启用 Inference。

## 2. 当前生产限制

第一版只运行一个 backend 副本，不要直接配置多实例负载均衡：

- LangGraph 使用 `InMemorySaver`，backend 重启会丢失进程内短期状态。
- MySQL 中的线程和消息仍然保留，但当前不会在重启后完整回灌 LangGraph checkpointer。
- Markdown Memory 没有跨进程文件锁，多个 backend 副本可能覆盖同一用户的文件。
- Auto Memory 使用进程内异步任务，容器在任务运行期间被强制停止可能导致该轮总结未执行。

这些限制不影响单实例部署，但在横向扩容前应将 checkpointer 和 Memory 写入迁移到支持并发控制的持久化存储。

## 3. 服务器要求

建议配置：

- Ubuntu 22.04/24.04 或兼容 Linux。
- 4 vCPU、8 GB RAM、40 GB 可用磁盘。
- Docker Engine 和 Docker Compose Plugin。
- 一个解析到服务器公网 IP 的域名。
- 对外开放 TCP `80`、`443`，并保留运维使用的 SSH 端口。
- 服务器可访问 OpenAI、Qdrant Cloud、Google APIs 和外部 MCP 地址。

Docker Compose 安装方式以官方文档为准：

- [Docker Compose installation](https://docs.docker.com/compose/install/)

检查安装：

```bash
docker --version
docker compose version
```

## 4. 服务器目录

推荐将代码部署到：

```text
/opt/finance-tech
```

```bash
sudo mkdir -p /opt/finance-tech
sudo chown "$USER":"$USER" /opt/finance-tech
git clone <your-repository-url> /opt/finance-tech
cd /opt/finance-tech
mkdir -p deploy secrets backups
```

本文档假设 `/opt/finance-tech` 就是包含 `backend/` 和 `frontend/` 的项目根目录。

最终需要以下部署文件：

```text
finance_tech/
├── backend/
├── frontend/
├── scripts/
├── deploy/
│   ├── backend.Dockerfile
│   ├── frontend.Dockerfile
│   └── Caddyfile
├── secrets/
│   └── google-adc.json
├── .dockerignore
├── .env.production
├── docker-compose.yml
└── deployment.md
```

`secrets/`、`.env.production`、本地上传文件和处理产物禁止提交到 Git。

## 5. Docker ignore

创建 `.dockerignore`：

```dockerignore
.git
.gitignore
.codegraph
.venv
**/__pycache__
**/*.pyc
**/.pytest_cache
**/.mypy_cache
frontend/node_modules
frontend/dist
backend/.env
backend/uploads
backend/processed
backend/memory
evaluations/results
output
secrets
.env.production
*.log
```

这可以避免把本地 Memory、上传文件、Google 凭证和 API Key 打进镜像。

## 6. Backend 镜像

创建 `deploy/backend.Dockerfile`：

```dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /tmp/requirements.txt

COPY backend /app/backend
COPY scripts /app/scripts

RUN useradd --system --uid 10001 --create-home appuser \
    && mkdir -p /app/backend/uploads /data/processed /data/memory \
    && chown -R appuser:appuser /app /data

USER appuser
WORKDIR /app/backend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
```

本地 MCP Server 不需要单独的容器。Backend 启动时会通过当前 Python 解释器执行：

```text
python -m app.mcp.local_server
```

## 7. Frontend 与 HTTPS 镜像

创建 `deploy/frontend.Dockerfile`：

```dockerfile
FROM node:20-alpine AS build

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend ./

ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build

FROM caddy:2.8-alpine

COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv

EXPOSE 80 443
```

`VITE_API_BASE_URL` 保持为空，前端会使用同域 `/api` 请求，避免浏览器直接访问容器内部地址。

## 8. Caddy 配置

创建 `deploy/Caddyfile`：

```caddyfile
{$DOMAIN} {
    encode zstd gzip

    header {
        -Server
        X-Content-Type-Options nosniff
        Referrer-Policy strict-origin-when-cross-origin
    }

    handle /api/* {
        reverse_proxy backend:8000 {
            flush_interval -1
        }
    }

    handle /health {
        reverse_proxy backend:8000
    }

    handle {
        root * /srv
        try_files {path} /index.html
        file_server
    }
}
```

`flush_interval -1` 用于及时转发 SSE 事件，避免 Agent token、工具事件和 Plan 步骤被代理缓冲。

Caddy 在域名有效、DNS 已指向服务器且 `80/443` 可访问时会自动申请并续期 HTTPS 证书：

- [Caddy Automatic HTTPS](https://caddyserver.com/docs/automatic-https)

## 9. Docker Compose

创建 `docker-compose.yml`：

```yaml
name: finance-tech

services:
  mysql:
    image: mysql:8.4
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      MYSQL_DATABASE: ${MYSQL_DATABASE}
      MYSQL_USER: ${MYSQL_USER}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
    volumes:
      - mysql_data:/var/lib/mysql
    healthcheck:
      test:
        [
          "CMD-SHELL",
          "mysqladmin ping -h 127.0.0.1 -uroot -p$$MYSQL_ROOT_PASSWORD --silent",
        ]
      interval: 10s
      timeout: 5s
      retries: 20
      start_period: 30s
    networks:
      - finance_internal

  db-init:
    image: finance-tech-backend:${APP_VERSION:-latest}
    env_file:
      - .env.production
    environment:
      MYSQL_HOST: mysql
      MYSQL_PORT: 3306
      MYSQL_USER: root
      MYSQL_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      MYSQL_DATABASE: ${MYSQL_DATABASE}
    command:
      [
        "python",
        "-c",
        "from app.model.db import init_database; init_database()",
      ]
    depends_on:
      mysql:
        condition: service_healthy
    restart: "no"
    networks:
      - finance_internal

  backend:
    image: finance-tech-backend:${APP_VERSION:-latest}
    build:
      context: .
      dockerfile: deploy/backend.Dockerfile
    restart: unless-stopped
    env_file:
      - .env.production
    environment:
      MYSQL_HOST: mysql
      MYSQL_PORT: 3306
      MYSQL_USER: ${MYSQL_USER}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
      MYSQL_DATABASE: ${MYSQL_DATABASE}
      MEMORY_DIR: /data/memory
      DOCUMENT_AI_ARTIFACT_DIR: /data/processed
      MCP_CONFIG_PATH: /app/backend/mcp_servers.json
      GOOGLE_APPLICATION_CREDENTIALS: /run/secrets/google-adc.json
    secrets:
      - google_adc
    volumes:
      - uploads_data:/app/backend/uploads
      - processed_data:/data/processed
      - memory_data:/data/memory
    depends_on:
      db-init:
        condition: service_completed_successfully
    expose:
      - "8000"
    healthcheck:
      test:
        [
          "CMD",
          "python",
          "-c",
          "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)",
        ]
      interval: 15s
      timeout: 6s
      retries: 10
      start_period: 40s
    networks:
      - finance_internal

  frontend:
    image: finance-tech-frontend:${APP_VERSION:-latest}
    build:
      context: .
      dockerfile: deploy/frontend.Dockerfile
      args:
        VITE_API_BASE_URL: ""
    restart: unless-stopped
    environment:
      DOMAIN: ${DOMAIN}
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"
    volumes:
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      backend:
        condition: service_healthy
    networks:
      - finance_internal

networks:
  finance_internal:
    driver: bridge

volumes:
  mysql_data:
  uploads_data:
  processed_data:
  memory_data:
  caddy_data:
  caddy_config:

secrets:
  google_adc:
    file: ./secrets/google-adc.json
```

MySQL 和 backend 不映射到宿主机端口，只能通过 Compose 内部网络访问。公网只暴露 Caddy 的 `80/443`。

`db-init` 使用 MySQL root 完成建库、幂等表迁移和默认用户初始化；正常运行的 backend 使用权限更小的应用用户。

## 10. 生产环境变量

创建 `.env.production`。以下值全部需要根据实际环境替换：

```env
# Compose and public endpoint
APP_VERSION=2026-07-06
DOMAIN=finance.example.com

# FastAPI
APP_ENV=production
APP_DEBUG=false
CORS_ORIGINS=["https://finance.example.com"]

# Authentication
JWT_SECRET_KEY=replace_with_at_least_32_random_bytes
JWT_EXPIRE_MINUTES=10080
DEFAULT_USER_EMAIL=admin@example.com
DEFAULT_USER_PASSWORD=replace_with_a_strong_password

# MySQL
MYSQL_ROOT_PASSWORD=replace_with_mysql_root_password
MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_DATABASE=finance_tech
MYSQL_USER=finance_app
MYSQL_PASSWORD=replace_with_mysql_app_password

# Chat model
OPENAI_API_KEY=replace_with_chat_api_key
OPENAI_MODEL=gpt-5.4-mini
OPENAI_STORE=false

# Embedding model
OPENAI_EMBEDDING_API_KEY=replace_with_embedding_api_key
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# Qdrant Managed Cloud
QDRANT_URL=https://replace-with-cluster-url
QDRANT_API_KEY=replace_with_qdrant_api_key
QDRANT_COLLECTION=finance_tech_chunks_hybrid_v1
QDRANT_CLOUD_INFERENCE=true
QDRANT_DENSE_VECTOR_NAME=dense
QDRANT_BM25_VECTOR_NAME=bm25
QDRANT_BM25_MODEL=Qdrant/bm25
QDRANT_BM25_LANGUAGE=none
QDRANT_BM25_TOKENIZER=multilingual
QDRANT_UPSERT_BATCH_SIZE=64
RAG_DENSE_CANDIDATE_COUNT=20
RAG_BM25_CANDIDATE_COUNT=20
RAG_FINAL_COUNT=4

# Google Document AI
DOCUMENT_AI_ENABLED=true
DOCUMENT_AI_PROJECT_ID=replace_with_gcp_project_id
DOCUMENT_AI_LOCATION=asia-southeast1
DOCUMENT_AI_OCR_PROCESSOR_ID=replace_with_ocr_processor_id
DOCUMENT_AI_FORM_PROCESSOR_ID=replace_with_form_processor_id
DOCUMENT_AI_PAGE_BATCH_SIZE=15
DOCUMENT_AI_BATCH_CONCURRENCY=2
DOCUMENT_AI_CALL_TIMEOUT_SECONDS=120
DOCUMENT_AI_TOTAL_TIMEOUT_SECONDS=600
DOCUMENT_AI_MAX_PAGES=200
DOCUMENT_AI_MAX_FILE_BYTES=104857600
DOCUMENT_AI_ARTIFACT_DIR=/data/processed

# Cross-page table stitching
TABLE_STITCHING_ENABLED=true
TABLE_STITCHING_MIN_SCORE=0.75

# MCP
MCP_CONFIG_PATH=/app/backend/mcp_servers.json
TAVILY_API_KEY=replace_with_tavily_api_key

# Long-term memory
MEMORY_ENABLED=true
MEMORY_DIR=/data/memory
MEMORY_DEFAULT_USER_ID=default
MEMORY_AUTO_TRIGGER_MESSAGE_COUNT=10
MEMORY_INDEX_MAX_LINES=200
MEMORY_INDEX_MAX_BYTES=25600
```

生成随机密钥：

```bash
openssl rand -hex 32
openssl rand -base64 36
```

限制配置文件权限：

```bash
chmod 600 .env.production
```

如果聊天模型通过 OpenAI 兼容中转服务访问，可以改用：

```env
OPENAI_RELAY_API_KEY=replace_with_relay_api_key
OPENAI_RELAY_BASE_URL=https://replace-with-relay-url/v1
OPENAI_RELAY_MODEL=replace_with_model_name
OPENAI_RELAY_STORE=false
```

Embedding 当前要求配置 `OPENAI_EMBEDDING_API_KEY` 或 `OPENAI_OFFICIAL_API_KEY`，不能只依赖 `OPENAI_API_KEY`。

## 11. Google ADC

生产环境优先使用以下方式：

1. 在 Google Cloud VM 上为实例绑定最小权限 Service Account，让 ADC 自动获取短期凭证。
2. 非 Google Cloud 环境使用 Workload Identity Federation。
3. 只有在无法使用前两种方式时，才挂载 Service Account JSON Key。

Google 官方建议优先使用附加服务账号或 Workload Identity，静态 Service Account Key 风险更高：

- [Google Cloud authentication](https://cloud.google.com/docs/authentication)

本 Compose 示例使用 JSON 文件，保存到：

```text
secrets/google-adc.json
```

并限制权限：

```bash
chmod 600 secrets/google-adc.json
```

该身份至少需要访问两个 Document AI Processor 的在线处理权限，并且 Processor 必须与 `DOCUMENT_AI_LOCATION` 位于同一区域。

如果暂时不处理 PDF，可以设置：

```env
DOCUMENT_AI_ENABLED=false
```

此时应同时从 Compose 中移除 `google_adc` secret 和 `GOOGLE_APPLICATION_CREDENTIALS`，否则缺失的 JSON 文件仍会阻止 Compose 启动。

## 12. 首次构建和启动

先验证 Compose 展开结果：

```bash
docker compose --env-file .env.production config
```

注意：该命令的输出可能包含展开后的敏感配置，不要粘贴到公开日志。

构建镜像：

```bash
docker compose --env-file .env.production build --pull backend frontend
```

启动：

```bash
docker compose --env-file .env.production up -d
```

查看状态：

```bash
docker compose --env-file .env.production ps
```

查看数据库初始化：

```bash
docker compose --env-file .env.production logs db-init
```

查看应用日志：

```bash
docker compose --env-file .env.production logs -f --tail=200 backend frontend
```

## 13. 验证部署

### 13.1 健康检查

```bash
curl -fsS "https://${DOMAIN}/health"
```

预期：

```json
{"status":"ok"}
```

### 13.2 前端

浏览器访问：

```text
https://finance.example.com
```

确认：

- 可以登录。
- 可以创建和恢复对话。
- Tools 页面能看到本地 MCP 工具。
- ReAct 能调用 `calculator`。
- SSE token 能持续显示，而不是最后一次性出现。

### 13.3 RAG

上传一份小型金融 PDF，确认：

- 文件状态最终为 `ready`。
- `processed/{file_id}` 生成 OCR、Form、Fusion、Table Stitching 和 Manifest JSON。
- Qdrant point 同时包含 `dense` 与 `bm25` 向量。
- 开启 RAG 后可以检索到文件名、页码和表格来源。

### 13.4 Memory

连续产生达到触发阈值的 user/assistant 消息后确认：

```bash
docker compose --env-file .env.production exec backend \
  sh -lc 'find /data/memory/users -maxdepth 2 -type f -print'
```

检查用户目录中是否生成：

```text
MEMORY.md
user-profile.md
financial-insights.md
finance-style.md
workflows.md
.state.json
```

## 14. 重建 Qdrant Hybrid 索引

预览：

```bash
docker compose --env-file .env.production exec backend \
  python /app/scripts/reindex_qdrant_hybrid.py --dry-run
```

执行：

```bash
docker compose --env-file .env.production exec backend \
  python /app/scripts/reindex_qdrant_hybrid.py \
  --target-collection finance_tech_chunks_hybrid_v1
```

重建前应先备份 MySQL，并确认 `processed_data` 中的 `fused.json` 完整。

## 15. 数据持久化与备份

需要备份：

- `mysql_data`：用户、线程、消息和文件记录。
- `uploads_data`：上传的原始文件。
- `processed_data`：Document AI 和 Fusion 审计产物。
- `memory_data`：用户长期 Markdown Memory。
- Qdrant Cloud collection：向量和 payload。

### 15.1 MySQL 备份

```bash
mkdir -p backups
docker compose --env-file .env.production exec -T mysql \
  sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
  > "backups/mysql-$(date +%Y%m%d-%H%M%S).sql"
```

### 15.2 文件卷备份

```bash
docker run --rm \
  -v finance-tech_uploads_data:/source:ro \
  -v "$PWD/backups":/backup \
  alpine:3.20 \
  tar czf /backup/uploads.tar.gz -C /source .

docker run --rm \
  -v finance-tech_processed_data:/source:ro \
  -v "$PWD/backups":/backup \
  alpine:3.20 \
  tar czf /backup/processed.tar.gz -C /source .

docker run --rm \
  -v finance-tech_memory_data:/source:ro \
  -v "$PWD/backups":/backup \
  alpine:3.20 \
  tar czf /backup/memory.tar.gz -C /source .
```

执行前用 `docker volume ls` 核对 Compose 实际生成的卷名。

## 16. 更新发布

先备份，然后执行：

```bash
cd /opt/finance-tech
git fetch --all --tags
git checkout <release-tag-or-commit>
docker compose --env-file .env.production build --pull backend frontend
docker compose --env-file .env.production up -d
docker compose --env-file .env.production ps
```

数据库初始化是幂等的，每次 `up` 时 `db-init` 都会检查并补充当前代码定义的表和索引。

部署完成后检查：

```bash
curl -fsS "https://${DOMAIN}/health"
docker compose --env-file .env.production logs --since=10m backend frontend
```

## 17. 回滚

1. 保留发布前的 Git commit、MySQL 备份和文件卷备份。
2. 切回上一版本 commit/tag。
3. 重新构建 backend/frontend 镜像。
4. 执行 `docker compose up -d`。
5. 如果新版本已经执行不可向后兼容的数据迁移，再恢复 MySQL 备份。

```bash
git checkout <previous-release>
docker compose --env-file .env.production build backend frontend
docker compose --env-file .env.production up -d
```

不要通过删除 Docker volume 的方式回滚。

## 18. 常见故障

### Backend 启动失败，提示本地 MCP 初始化失败

```bash
docker compose --env-file .env.production logs backend
docker compose --env-file .env.production exec backend \
  python -m app.mcp.local_server
```

检查 Python 依赖、工作目录和本地 MCP Server 是否能启动。远程 MCP 加载失败会被跳过，本地 MCP 加载失败会阻止 backend 启动。

### Qdrant BM25 inference 失败

确认：

- `QDRANT_URL` 和 API Key 正确。
- Qdrant Cloud 集群已启用 Inference。
- 集群支持 `Qdrant/bm25`。
- collection schema 中同时存在命名向量 `dense` 和稀疏向量 `bm25`。

参考：

- [Qdrant Managed Cloud Inference](https://qdrant.tech/documentation/cloud/inference/)

### Google ADC not found

```bash
docker compose --env-file .env.production exec backend \
  sh -lc 'test -r "$GOOGLE_APPLICATION_CREDENTIALS" && echo readable'
```

检查 `secrets/google-adc.json` 是否存在、权限是否正确，以及 Compose secret 是否挂载成功。

### Document AI PermissionDenied 或 NotFound

检查：

- Service Account 是否具有 Processor Online Process 权限。
- Processor ID、项目和区域是否匹配。
- API 是否已启用。
- Processor 是否位于 `DOCUMENT_AI_LOCATION` 指定区域。

### MySQL Access denied

```bash
docker compose --env-file .env.production logs mysql db-init
```

如果修改过 MySQL 用户密码，已有 `mysql_data` 不会自动应用新的初始化密码。应在数据库中修改用户密码，或在确认不需要历史数据时重新初始化卷。

### 前端可以打开，但 API 请求失败

```bash
curl -fsS "https://${DOMAIN}/health"
docker compose --env-file .env.production logs frontend backend
```

确认前端镜像构建时 `VITE_API_BASE_URL` 为空，并且浏览器请求地址是同域 `/api/...`。

### SSE 最后一次性返回

确认 Caddy 的 backend `reverse_proxy` 包含：

```caddyfile
flush_interval -1
```

如果 Caddy 前面还有 CDN 或负载均衡，也要关闭该层对 `text/event-stream` 的响应缓冲。

### 上传大文件失败

检查：

- `DOCUMENT_AI_MAX_FILE_BYTES`。
- 云服务器或上游负载均衡的请求体限制。
- Document AI 单批限制和总处理超时。
- `processed_data` 和 `uploads_data` 的剩余空间。

## 19. 上线检查清单

- [ ] `.env.production` 和 Google 凭证未提交 Git。
- [ ] `APP_ENV=production`、`APP_DEBUG=false`。
- [ ] JWT、MySQL、OpenAI、Qdrant 和 Tavily 密钥已替换。
- [ ] DNS 已指向服务器，`80/443` 已开放。
- [ ] Caddy HTTPS 证书签发成功。
- [ ] MySQL、上传文件、处理产物和 Memory 使用持久化卷。
- [ ] Qdrant Cloud Inference 已启用。
- [ ] Google ADC 可读且权限最小化。
- [ ] `/health`、登录、SSE、MCP、PDF 上传、RAG 和 Memory 均完成验收。
- [ ] 已执行首次完整备份并验证恢复流程。
- [ ] Backend 保持单副本运行。

