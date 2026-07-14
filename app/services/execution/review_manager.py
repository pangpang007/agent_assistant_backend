import asyncio
import json
import structlog
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.config import settings

logger = structlog.get_logger()


class ReviewManager:
    """审核暂停/恢复管理（Redis Pub/Sub）。"""

    def __init__(self, redis):
        self.redis = redis
        self._events: dict[str, asyncio.Event] = {}

    async def wait_for_review(
        self,
        execution_id,
        node_id: str,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        if timeout is None:
            timeout = settings.review_default_timeout
        channel = f"review:{execution_id}"
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(channel)

        try:
            async with asyncio.timeout(timeout):
                while True:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0,
                    )
                    if message and message["type"] == "message":
                        data = json.loads(message["data"])
                        if data.get("node_id") == node_id:
                            return data
                    await asyncio.sleep(0.1)
        except TimeoutError:
            return {"action": "timeout", "comment": "审核超时"}
        finally:
            await pubsub.unsubscribe(channel)
            close = getattr(pubsub, "aclose", None) or getattr(pubsub, "close", None)
            if close:
                await close()

    async def submit_review(
        self,
        execution_id,
        node_id: str,
        action: str,
        comment: Optional[str] = None,
        modified_data: Optional[dict] = None,
    ) -> None:
        channel = f"review:{execution_id}"
        result = {
            "node_id": node_id,
            "action": action,
            "comment": comment,
            "modified_data": modified_data,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.redis.publish(channel, json.dumps(result, ensure_ascii=False))
        logger.info(
            "review_submitted",
            execution_id=str(execution_id),
            node_id=node_id,
            action=action,
        )
