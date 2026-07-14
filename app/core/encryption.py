"""Fernet 对称加密工具，用于加密/解密 API Key 等敏感数据。"""

import structlog
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.exceptions import AppException

logger = structlog.get_logger()


def _get_fernet() -> Fernet:
    key = (
        settings.fernet_key.encode()
        if isinstance(settings.fernet_key, str)
        else settings.fernet_key
    )
    try:
        return Fernet(key)
    except Exception as e:
        logger.error("invalid_fernet_key", error=str(e))
        raise AppException(
            code="ENCRYPTION_CONFIG_ERROR",
            message="服务器加密配置无效，请检查 FERNET_KEY",
            status_code=500,
        ) from e


def encrypt_value(plain_text: str) -> str:
    """加密明文，返回 base64 编码的加密字符串。"""
    if plain_text is None:
        raise AppException(
            code="ENCRYPTION_ERROR",
            message="无法加密空值",
            status_code=400,
        )
    try:
        return _get_fernet().encrypt(plain_text.encode("utf-8")).decode("utf-8")
    except AppException:
        raise
    except Exception as e:
        logger.error("encrypt_failed", error=str(e))
        raise AppException(
            code="ENCRYPTION_ERROR",
            message="敏感数据加密失败",
            status_code=500,
        ) from e


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
