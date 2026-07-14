"""Redis cache invalidation helpers for Phase 7."""

from __future__ import annotations

import structlog

from app.core.api_key_auth import hash_api_key

logger = structlog.get_logger()


async def _get_redis_safe():
    try:
        from app.core.redis import get_redis

        return get_redis()
    except Exception:
        return None


class CacheInvalidator:
    """缓存失效管理器"""

    @staticmethod
    async def invalidate_dashboard(user_id: str) -> None:
        redis = await _get_redis_safe()
        if redis is None:
            return
        try:
            await redis.delete(f"dashboard:stats:{user_id}")
            cursor = 0
            while True:
                cursor, keys = await redis.scan(
                    cursor, match=f"dashboard:token_usage:{user_id}:*", count=100
                )
                if keys:
                    await redis.delete(*keys)
                if cursor == 0:
                    break
        except Exception as exc:
            logger.warning("cache_invalidate_dashboard_failed", error=str(exc))

    @staticmethod
    async def invalidate_api_key(api_key: str) -> None:
        redis = await _get_redis_safe()
        if redis is None or not api_key:
            return
        try:
            await redis.delete(f"api_key:{hash_api_key(api_key)}")
        except Exception as exc:
            logger.warning("cache_invalidate_api_key_failed", error=str(exc))

    @staticmethod
    async def invalidate_search(user_id: str) -> None:
        redis = await _get_redis_safe()
        if redis is None:
            return
        try:
            cursor = 0
            while True:
                cursor, keys = await redis.scan(
                    cursor, match=f"search:{user_id}:*", count=100
                )
                if keys:
                    await redis.delete(*keys)
                if cursor == 0:
                    break
        except Exception as exc:
            logger.warning("cache_invalidate_search_failed", error=str(exc))
