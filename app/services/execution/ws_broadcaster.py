import asyncio
import json
import structlog
import uuid
from typing import Any

from fastapi import WebSocket

logger = structlog.get_logger()


class ConnectionManager:
    """WebSocket 连接管理器（单例）。"""

    def __init__(self):
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, execution_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            if execution_id not in self._connections:
                self._connections[execution_id] = set()
            self._connections[execution_id].add(websocket)
        logger.info("ws_connected", execution_id=execution_id)

    async def disconnect(self, execution_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            if execution_id in self._connections:
                self._connections[execution_id].discard(websocket)
                if not self._connections[execution_id]:
                    del self._connections[execution_id]
        logger.info("ws_disconnected", execution_id=execution_id)

    async def broadcast(self, execution_id: uuid.UUID | str, message: dict[str, Any]) -> None:
        exec_id = str(execution_id)
        async with self._lock:
            connections = self._connections.get(exec_id, set()).copy()

        if not connections:
            return

        message_json = json.dumps(message, ensure_ascii=False, default=str)
        dead_connections: list[WebSocket] = []

        for ws in connections:
            try:
                await ws.send_text(message_json)
            except Exception:
                dead_connections.append(ws)

        if dead_connections:
            async with self._lock:
                for ws in dead_connections:
                    if exec_id in self._connections:
                        self._connections[exec_id].discard(ws)

    def get_connection_count(self, execution_id: str) -> int:
        return len(self._connections.get(execution_id, set()))


ws_manager = ConnectionManager()


class WSBroadcaster:
    """WorkflowExecutor 使用的广播器封装。"""

    def __init__(self, manager: ConnectionManager | None = None):
        self._manager = manager or ws_manager

    async def broadcast(self, execution_id: uuid.UUID | str, message: dict[str, Any]) -> None:
        await self._manager.broadcast(execution_id, message)
