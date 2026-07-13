from fastapi import APIRouter
from sqlalchemy import text

from app.core.database import engine
from app.core.redis import get_redis

router = APIRouter()


@router.get("/health")
async def health_check():
    """
    健康检查接口。
    返回 status、数据库连接状态、Redis 连接状态。
    """
    checks = {}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "connected"
    except Exception as e:
        checks["database"] = f"error: {str(e)}"

    try:
        r = get_redis()
        await r.ping()
        checks["redis"] = "connected"
    except Exception as e:
        checks["redis"] = f"error: {str(e)}"

    all_ok = all(v == "connected" for v in checks.values())

    return {
        "status": "healthy" if all_ok else "degraded",
        "version": "0.1.0",
        "checks": checks,
    }
