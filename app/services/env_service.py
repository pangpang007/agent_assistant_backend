import re
import uuid
from typing import Optional

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_value, encrypt_value
from app.core.exceptions import (
    EnvVarKeyExistsError,
    EnvVarKeyFormatError,
    EnvVarNotFoundError,
    EnvVarTypeImmutableError,
    ForbiddenException,
)
from app.models.enums import EnvVarType
from app.models.env_variable import EnvVariable
from app.schemas.env_variable import EnvVarListItem, EnvVarListResponse, EnvVarResponse

logger = structlog.get_logger()

_KEY_PATTERN = re.compile(r"^[A-Z0-9_]+$")


def mask_secret_value(plain: str) -> str:
    """脱敏 secret：**** + 最后 4 位。"""
    if not plain:
        return "****"
    last4 = plain[-4:] if len(plain) >= 4 else plain
    return f"****{last4}"


def format_env_var(env_var: EnvVariable) -> EnvVarResponse:
    var_type = env_var.type.value if hasattr(env_var.type, "value") else str(env_var.type)
    decrypted = decrypt_value(env_var.value_encrypted)
    if var_type == "secret":
        return EnvVarResponse(
            id=env_var.id,
            key=env_var.key,
            type=var_type,
            value=None,
            masked_value=mask_secret_value(decrypted) if decrypted else "****",
            created_at=env_var.created_at,
            updated_at=env_var.updated_at,
        )
    return EnvVarResponse(
        id=env_var.id,
        key=env_var.key,
        type=var_type,
        value=decrypted,
        masked_value=None,
        created_at=env_var.created_at,
        updated_at=env_var.updated_at,
    )


class EnvService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_env_vars(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 50,
        var_type: Optional[str] = None,
    ) -> EnvVarListResponse:
        query = select(EnvVariable).where(EnvVariable.user_id == user_id)
        count_query = select(func.count(EnvVariable.id)).where(
            EnvVariable.user_id == user_id
        )

        if var_type:
            query = query.where(EnvVariable.type == var_type)
            count_query = count_query.where(EnvVariable.type == var_type)

        query = query.order_by(EnvVariable.key.asc())
        total = (await self.db.execute(count_query)).scalar() or 0
        offset = (page - 1) * page_size
        result = await self.db.execute(query.offset(offset).limit(page_size))
        env_vars = result.scalars().all()

        items = [
            EnvVarListItem(**format_env_var(ev).model_dump()) for ev in env_vars
        ]
        return EnvVarListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            has_next=offset + page_size < total,
        )

    async def create_env_var(
        self,
        user_id: uuid.UUID,
        key: str,
        value: str,
        var_type: str = "string",
    ) -> EnvVariable:
        if not _KEY_PATTERN.match(key):
            raise EnvVarKeyFormatError()

        existing = await self.db.execute(
            select(EnvVariable).where(
                EnvVariable.user_id == user_id,
                EnvVariable.key == key,
            )
        )
        if existing.scalar_one_or_none():
            raise EnvVarKeyExistsError()

        env_var = EnvVariable(
            user_id=user_id,
            key=key,
            value_encrypted=encrypt_value(value),
            type=EnvVarType(var_type),
        )
        self.db.add(env_var)
        await self.db.flush()
        logger.info("env_var_created", key=key, type=var_type)
        return env_var

    async def update_env_var(
        self,
        env_var_id: uuid.UUID,
        user_id: uuid.UUID,
        value: Optional[str] = None,
        var_type: Optional[str] = None,
    ) -> EnvVariable:
        env_var = await self._get_owned(env_var_id, user_id)

        if var_type is not None:
            current_type = (
                env_var.type.value if hasattr(env_var.type, "value") else env_var.type
            )
            if var_type != current_type:
                raise EnvVarTypeImmutableError()

        if value is not None:
            env_var.value_encrypted = encrypt_value(value)

        await self.db.flush()
        return env_var

    async def delete_env_var(
        self, env_var_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        env_var = await self._get_owned(env_var_id, user_id)
        await self.db.delete(env_var)
        await self.db.flush()

    async def _get_owned(
        self, env_var_id: uuid.UUID, user_id: uuid.UUID
    ) -> EnvVariable:
        result = await self.db.execute(
            select(EnvVariable).where(EnvVariable.id == env_var_id)
        )
        env_var = result.scalar_one_or_none()
        if not env_var:
            raise EnvVarNotFoundError()
        if env_var.user_id != user_id:
            raise ForbiddenException("无权操作此环境变量")
        return env_var
