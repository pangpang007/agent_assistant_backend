"""Fernet 对称加密工具，用于加密/解密 API Key 等敏感数据。"""

import structlog
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = structlog.get_logger()


def _get_fernet() -> Fernet:
    key = (
        settings.fernet_key.encode()
        if isinstance(settings.fernet_key, str)
        else settings.fernet_key
    )
    return Fernet(key)


def encrypt_value(plain_text: str) -> str:
    """加密明文，返回 base64 编码的加密字符串。"""
    return _get_fernet().encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_value(encrypted_text: str) -> str:
    """解密密文，失败时返回空字符串。"""
    if not encrypted_text:
        return ""
    try:
        return _get_fernet().decrypt(encrypted_text.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception) as e:
        logger.warning("decrypt_failed", error=str(e))
        return ""


def mask_api_key(api_key: str) -> str:
    """脱敏 API Key：显示前 3 位和后 4 位。"""
    if not api_key or len(api_key) < 8:
        return "****"
    return f"{api_key[:3]}****{api_key[-4:]}"
