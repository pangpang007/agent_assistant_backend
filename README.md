# 汤圆的代码助手 - 后端 (tangyuan-backend)

Phase 0 后端脚手架：FastAPI + PostgreSQL (pgvector) + Redis。

## 本地开发启动

```bash
# 1. 创建虚拟环境（需要 Python 3.11+）
python3.11 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 复制环境配置
cp .env.example .env
# 编辑 .env 填写实际配置

# 生成 Fernet 密钥（填入 .env 的 FERNET_KEY）:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 4. 启动 Docker 服务（PostgreSQL + Redis）
docker compose up -d db redis

# 5. 运行数据库迁移
alembic upgrade head

# 6. 启动开发服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 健康检查

```bash
curl http://localhost:8000/api/health
```

## 运行测试

```bash
pytest tests/
```

## API 文档

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
