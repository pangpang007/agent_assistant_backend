import uuid


class CancellationManager:
    """通过 Redis 管理执行取消标志。"""

    def __init__(self, redis):
        self.redis = redis
        self._ttl = 86400

    def _key(self, execution_id: uuid.UUID | str) -> str:
        return f"cancel:{execution_id}"

    async def set_cancelled(self, execution_id: uuid.UUID | str) -> None:
        await self.redis.set(self._key(execution_id), "1", ex=self._ttl)

    async def is_cancelled(self, execution_id: uuid.UUID | str) -> bool:
        return await self.redis.get(self._key(execution_id)) is not None

    async def clear_cancelled(self, execution_id: uuid.UUID | str) -> None:
        await self.redis.delete(self._key(execution_id))
