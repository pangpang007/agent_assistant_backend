import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from cryptography.fernet import Fernet
from jose import JWTError, jwt

from app.core.config import settings
from app.core.redis import get_redis


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
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "account_type": account_type,
        "team_id": team_id,
        "username": username,
        "type": "access",
        "iat": now,
        "jti": str(uuid.uuid4()),
    }
    expire = now + (
        expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    payload["exp"] = expire
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(
    user_id: str,
    email: str,
    account_type: str,
    team_id: str | None,
    username: str,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "account_type": account_type,
        "team_id": team_id,
        "username": username,
        "type": "refresh",
        "iat": now,
        "jti": str(uuid.uuid4()),
    }
    expire = now + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload["exp"] = expire
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        return None


def generate_invite_code(length: int | None = None) -> str:
    code_length = length or settings.invite_code_length
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(code_length))


async def blacklist_token(token: str, expires_at: datetime) -> None:
    redis = get_redis()
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    key = f"token_blacklist:{token_hash}"

    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    ttl_seconds = int((expires_at - now).total_seconds())

    if ttl_seconds > 0:
        await redis.setex(key, ttl_seconds, "revoked")


async def is_token_blacklisted(token: str) -> bool:
    redis = get_redis()
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    key = f"token_blacklist:{token_hash}"
    result = await redis.get(key)
    return result is not None


def _get_fernet() -> Fernet:
    return Fernet(settings.fernet_key.encode())


def encrypt_value(value: str) -> str:
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt_value(encrypted_value: str) -> str:
    return _get_fernet().decrypt(encrypted_value.encode()).decode()
