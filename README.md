# 汤圆的代码助手 - 后端

FastAPI 后端：PostgreSQL (pgvector) + Redis + Celery。已实现 Phase 0–4（用户系统、Agent/Tool/Model、知识库 RAG、工作流编辑器）。

## 技术栈

| 组件 | 用途 |
|------|------|
| FastAPI | HTTP API |
| PostgreSQL + pgvector | 主库、向量检索 |
| Redis | JWT 黑名单、Celery 队列 |
| Celery | 知识库文档异步处理 |
| Cloudflare Tunnel（可选） | 对外暴露 API 域名 |

---

## NAS 生产部署（推荐）

在 NAS 上 clone 仓库后，使用部署脚本一键完成构建、启动和迁移：

```bash
git clone https://github.com/pangpang007/agent_assistant_backend.git
cd agent_assistant_backend

# 首次部署：创建 .env → 编辑配置 → 再次执行
sudo ./scripts/deploy.sh --init

# 日常更新
sudo ./scripts/deploy.sh

# 仅重启（改了 .env、不需要重新构建时）
sudo ./scripts/deploy.sh --restart
```

### `.env` 必填项

从 `.env.example` 复制后至少修改：

- `POSTGRES_PASSWORD` — 数据库密码
- `SECRET_KEY` / `JWT_SECRET_KEY` / `FERNET_KEY` — 安全密钥
- `CORS_ORIGINS` — 前端域名，如 `["https://app.yourdomain.com"]`
- `CLOUDFLARE_TUNNEL_TOKEN` — 使用 Tunnel 时填写（Zero Trust → Tunnels → Docker Token）

生成 Fernet 密钥：

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Cloudflare Tunnel

`.env` 中配置了 `CLOUDFLARE_TUNNEL_TOKEN` 后，脚本会自动启用 `cloudflared` 容器。

在 Cloudflare 控制台将 Public Hostname 的 Service URL 设为：

```text
http://api:8000
```

### 手动 compose（可选）

```bash
sudo docker compose -f docker-compose.prod.yml --profile tunnel up -d --build
sudo docker compose -f docker-compose.prod.yml exec api alembic upgrade head
```

生产 compose 包含：`db`、`redis`、`api`、`celery`、（可选）`cloudflared`。

---

## 本地开发

```bash
# 1. 创建虚拟环境（Python 3.11+）
python3.11 -m venv .venv
source .venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 环境配置
cp .env.example .env
# 编辑 .env；本地开发 DATABASE_URL / REDIS_URL 使用 localhost

# 4. 启动 PostgreSQL + Redis
docker compose up -d db redis

# 5. 数据库迁移
alembic upgrade head

# 6. 启动 API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 7. 知识库文档处理（另开终端）
celery -A app.core.celery_app worker --loglevel=info --queues=knowledge --concurrency=4
```

---

## 健康检查

```bash
curl http://localhost:8000/api/health
```

---

## 运行测试

```bash
pytest tests/
```

---

## API 文档

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## 项目结构

```text
app/                  应用代码
alembic/              数据库迁移
docs/                 各 Phase 设计文档
scripts/deploy.sh     NAS 部署脚本
docker-compose.yml        本地开发（db + redis）
docker-compose.prod.yml   NAS 生产（db + redis + api + celery + tunnel）
```
