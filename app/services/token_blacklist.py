"""Redis-backed JWT jti blacklist."""

import logging
import time

from app.core.config import settings

logger = logging.getLogger(__name__)


class TokenBlacklistService:
    """基于 Redis 的 Token 黑名单，用于主动使 JWT 失效。"""

    @classmethod
    def _key(cls, jti: str) -> str:
        return f"{settings.redis_token_blacklist_prefix}:{jti}"

    @classmethod
    async def blacklist(cls, jti: str, exp: int) -> None:
        """
        将 token 加入黑名单。

        TTL = max(exp - now, 1)。写入失败仅记日志，不阻断请求。
        """
        now = int(time.time())
        ttl = max(int(exp) - now, 1)

        try:
            from app.core.redis import get_redis

            redis = get_redis()
            await redis.set(cls._key(jti), "1", ex=ttl)
            logger.info("Token blacklisted: jti=%s, ttl=%ss", jti, ttl)
        except Exception as exc:
            logger.warning(
                "Token blacklist write failed (ignored): jti=%s, error=%s",
                jti,
                exc,
            )

    @classmethod
    async def is_blacklisted(cls, jti: str) -> bool:
        """
        检查 jti 是否在黑名单中。

        读取失败时降级为未黑名单（放行），避免 Redis 故障导致全站不可用。
        """
        try:
            from app.core.redis import get_redis

            redis = get_redis()
            value = await redis.get(cls._key(jti))
            return value is not None
        except Exception as exc:
            logger.error(
                "Token blacklist read failed (fail-open): jti=%s, error=%s",
                jti,
                exc,
            )
            return False

    @classmethod
    async def remove(cls, jti: str) -> None:
        """从黑名单移除（极少使用）。"""
        try:
            from app.core.redis import get_redis

            redis = get_redis()
            await redis.delete(cls._key(jti))
            logger.info("Token removed from blacklist: jti=%s", jti)
        except Exception as exc:
            logger.warning(
                "Token blacklist remove failed (ignored): jti=%s, error=%s",
                jti,
                exc,
            )
