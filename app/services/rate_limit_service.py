"""Per-API-key rate limiting for external published runs."""

from __future__ import annotations

from app.core.config import settings


def is_over_limit(count: int, limit: int) -> bool:
    """Pure helper: whether count exceeds limit."""
    return count > limit


def remaining_quota(count: int, limit: int) -> int:
    """Pure helper: remaining allowance."""
    return max(0, limit - count)


class RateLimitService:
    """
    API Key 级别限流。

    - 每分钟最多 RATE_LIMIT_PER_MINUTE_EXTERNAL 次
    - 每天最多 RATE_LIMIT_PER_DAY_EXTERNAL 次
    """

    async def check_rate_limit(self, api_key: str) -> tuple[bool, dict]:
        per_minute = settings.rate_limit_per_minute_external
        per_day = settings.rate_limit_per_day_external

        try:
            from app.core.redis import get_redis

            redis = get_redis()
        except Exception:
            return True, {
                "remaining_minute": per_minute,
                "remaining_day": per_day,
                "retry_after": None,
            }

        minute_key = f"rate_limit:{api_key}:minute"
        day_key = f"rate_limit:{api_key}:day"

        minute_count = await redis.incr(minute_key)
        if minute_count == 1:
            await redis.expire(minute_key, 60)

        day_count = await redis.incr(day_key)
        if day_count == 1:
            await redis.expire(day_key, 86400)

        remaining_minute = remaining_quota(minute_count, per_minute)
        remaining_day = remaining_quota(day_count, per_day)

        if is_over_limit(minute_count, per_minute):
            ttl = await redis.ttl(minute_key)
            return False, {
                "remaining_minute": 0,
                "remaining_day": remaining_day,
                "retry_after": max(1, ttl),
            }

        if is_over_limit(day_count, per_day):
            return False, {
                "remaining_minute": remaining_minute,
                "remaining_day": 0,
                "retry_after": 86400,
            }

        return True, {
            "remaining_minute": remaining_minute,
            "remaining_day": remaining_day,
            "retry_after": None,
        }
