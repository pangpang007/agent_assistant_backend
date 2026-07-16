import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from cryptography.fernet import Fernet
from jose import ExpiredSignatureError, JWTError, jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def validate_password_strength(password: str) -> list[str]:
    errors = []
    if len(password) < 8:
        errors.append("密码长度至少为 8 位")
    if len(password) > 128:
        errors.append("密码长度不能超过 128 位")
    if not re.search(r"[A-Z]", password):
        errors.append("密码必须包含至少一个大写字母")
    if not re.search(r"[a-z]", password):
        errors.append("密码必须包含至少一个小写字母")
    if not re.search(r"[0-9]", password):
        errors.append("密码必须包含至少一个数字")
    return errors


def create_access_token(
    user_id: str,
    email: str,
    account_type: str,
    team_id: str | None,
    username: str,
    expires_delta: Optional[timedelta] = None,
) -> tuple[str, dict]:
    """
    创建 access token。

    Returns:
        (encoded_token, payload_dict)
    """
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    payload = {
        "sub": str(user_id),
        "email": email,
        "account_type": account_type,
        "team_id": team_id,
        "username": username,
        "type": "access",
        "token_type": "access",
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    encoded = jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )
    return encoded, payload


def create_refresh_token(
    user_id: str,
    email: str,
    account_type: str,
    team_id: str | None,
    username: str,
    expires_delta: Optional[timedelta] = None,
) -> tuple[str, dict]:
    """
    创建 refresh token。

    Returns:
        (encoded_token, payload_dict)
    """
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta or timedelta(days=settings.jwt_refresh_token_expire_days)
    )
    payload = {
        "sub": str(user_id),
        "email": email,
        "account_type": account_type,
        "team_id": team_id,
        "username": username,
        "type": "refresh",
        "token_type": "refresh",
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    encoded = jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )
    return encoded, payload


def create_token_pair(
    user_id: str,
    email: str,
    account_type: str,
    team_id: str | None,
    username: str,
) -> tuple[str, dict, str, dict]:
    """Create access + refresh token pair from user claims."""
    access_token, access_payload = create_access_token(
        user_id=user_id,
        email=email,
        account_type=account_type,
        team_id=team_id,
        username=username,
    )
    refresh_token, refresh_payload = create_refresh_token(
        user_id=user_id,
        email=email,
        account_type=account_type,
        team_id=team_id,
        username=username,
    )
    return access_token, access_payload, refresh_token, refresh_payload


def create_token_pair_from_claims(claims: dict) -> tuple[str, dict, str, dict]:
    """Recreate token pair using claims from an existing token payload."""
    return create_token_pair(
        user_id=str(claims["sub"]),
        email=claims.get("email", ""),
        account_type=claims.get("account_type", "personal"),
        team_id=claims.get("team_id"),
        username=claims.get("username", ""),
    )


def decode_token(token: str) -> dict:
    """
    解码并验证 JWT。

    Raises:
        ExpiredSignatureError: token 已过期
        JWTError: token 无效
    """
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )


def try_decode_token(token: str) -> Optional[dict]:
    """解码 JWT，失败时返回 None（兼容旧调用方）。"""
    try:
        return decode_token(token)
    except JWTError:
        return None


def decode_token_unverified_exp(token: str) -> Optional[dict]:
    """解码 JWT，不校验过期（用于登出黑名单等）。"""
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False},
        )
    except JWTError:
        return None


def get_token_type(payload: dict) -> str | None:
    """兼容 type / token_type 字段。"""
    return payload.get("token_type") or payload.get("type")


def generate_invite_code(length: int | None = None) -> str:
    code_length = length or settings.invite_code_length
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(code_length))


async def blacklist_token(token: str, expires_at: datetime | int | None = None) -> None:
    """将 token 的 jti 加入黑名单（兼容旧接口）。"""
    from app.services.token_blacklist import TokenBlacklistService

    payload = decode_token_unverified_exp(token)
    if not payload:
        return

    jti = payload.get("jti")
    if not jti:
        return

    if expires_at is None:
        exp = int(payload.get("exp", 0))
    elif isinstance(expires_at, datetime):
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        exp = int(expires_at.timestamp())
    else:
        exp = int(expires_at)

    await TokenBlacklistService.blacklist(jti, exp)


async def is_token_blacklisted(token: str) -> bool:
    """检查 token 的 jti 是否在黑名单中（兼容旧接口）。"""
    from app.services.token_blacklist import TokenBlacklistService

    payload = decode_token_unverified_exp(token)
    if not payload:
        return False

    jti = payload.get("jti")
    if not jti:
        return False

    return await TokenBlacklistService.is_blacklisted(jti)


def _get_fernet() -> Fernet:
    return Fernet(settings.fernet_key.encode())


def encrypt_value(value: str) -> str:
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt_value(encrypted_value: str) -> str:
    return _get_fernet().decrypt(encrypted_value.encode()).decode()


__all__ = [
    "ExpiredSignatureError",
    "JWTError",
    "hash_password",
    "verify_password",
    "validate_password_strength",
    "create_access_token",
    "create_refresh_token",
    "create_token_pair",
    "create_token_pair_from_claims",
    "decode_token",
    "try_decode_token",
    "decode_token_unverified_exp",
    "get_token_type",
    "generate_invite_code",
    "blacklist_token",
    "is_token_blacklisted",
    "encrypt_value",
    "decrypt_value",
]
