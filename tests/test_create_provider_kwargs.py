"""Regression: create_provider must not pass duplicate base_url kwargs."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.model_service import ModelService


@pytest.mark.asyncio
async def test_create_provider_with_base_url_no_typeerror(monkeypatch):
    captured = {}

    class FakeProvider:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.id = uuid.uuid4()
            self.provider_name = kwargs["provider_name"]
            self.provider_type = kwargs["provider_type"]

    monkeypatch.setattr("app.services.model_service.ModelProvider", FakeProvider)
    monkeypatch.setattr(
        "app.services.model_service.encrypt_value", lambda x: f"enc({x})"
    )

    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    await ModelService.create_provider(
        db=db,
        user_id=uuid.uuid4(),
        data={
            "provider_name": "OpenAI",
            "provider_type": "openai",
            "api_key": "sk-test-key",
            "base_url": "https://api.openai.com/v1",
            "models": [],
        },
    )

    assert captured["base_url"] == "https://api.openai.com/v1"
    assert captured["api_key_encrypted"] == "enc(sk-test-key)"
    assert "models" not in captured
