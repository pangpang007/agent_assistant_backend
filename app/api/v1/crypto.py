"""公钥下发：前端获取 RSA-OAEP public key 后加密敏感字段。"""

from fastapi import APIRouter

from app.core.transport_crypto import get_public_key_payload

router = APIRouter()


@router.get("/public-key")
async def get_transport_public_key():
    return {
        "code": 0,
        "message": "success",
        "data": get_public_key_payload(),
    }
