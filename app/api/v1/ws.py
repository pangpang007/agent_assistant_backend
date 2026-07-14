import json
import uuid

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.database import async_session_factory
from app.core.security import decode_token
from app.models.execution import Execution
from app.models.workflow import Workflow
from app.services.execution.ws_broadcaster import ws_manager

logger = structlog.get_logger()
router = APIRouter()


@router.websocket("/executions/{execution_id}")
async def execution_ws(
    websocket: WebSocket,
    execution_id: uuid.UUID,
    token: str = Query(..., description="JWT access token"),
):
    """
    WebSocket 实时推送工作流执行状态。
    路径: /api/ws/executions/{execution_id}
    """
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        await websocket.close(code=4001, reason="Invalid token")
        return

    user_id_str = payload.get("sub")
    if not user_id_str:
        await websocket.close(code=4001, reason="Invalid token")
        return

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        await websocket.close(code=4001, reason="Invalid token")
        return

    async with async_session_factory() as db:
        execution = await db.get(Execution, execution_id)
        if not execution:
            await websocket.close(code=4004, reason="Execution not found")
            return

        workflow = (
            await db.execute(
                select(Workflow).where(Workflow.id == execution.workflow_id)
            )
        ).scalar_one_or_none()
        if not workflow or workflow.user_id != user_id:
            await websocket.close(code=4003, reason="Forbidden")
            return

    exec_id = str(execution_id)
    await ws_manager.connect(exec_id, websocket)

    try:
        await websocket.send_text(
            json.dumps(
                {
                    "type": "connected",
                    "execution_id": exec_id,
                    "message": "已连接到执行流",
                },
                ensure_ascii=False,
            )
        )

        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                if message.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "error",
                            "code": "INVALID_MESSAGE",
                            "message": "Invalid JSON message",
                        }
                    )
                )
    except WebSocketDisconnect:
        await ws_manager.disconnect(exec_id, websocket)
    except Exception as exc:
        logger.error("ws_error", execution_id=exec_id, error=str(exc))
        await ws_manager.disconnect(exec_id, websocket)
