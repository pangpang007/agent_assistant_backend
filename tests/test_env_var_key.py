import pytest
from pydantic import ValidationError

from app.schemas.env_variable import EnvVarCreateRequest
from app.services.env_service import mask_secret_value


class TestEnvVarKeyPattern:
    def test_valid_keys(self):
        for key in ("OPENAI_API_KEY", "VALID_KEY_123", "A", "_X"):
            req = EnvVarCreateRequest(key=key, value="secret", type="string")
            assert req.key == key

    def test_invalid_lowercase(self):
        with pytest.raises(ValidationError):
            EnvVarCreateRequest(key="abc", value="x", type="string")

    def test_invalid_hyphen(self):
        with pytest.raises(ValidationError):
            EnvVarCreateRequest(key="BAD-KEY", value="x", type="string")


class TestMaskSecretValue:
    def test_mask_last4(self):
        assert mask_secret_value("sk-abcdefgh") == "****efgh"

    def test_short_value(self):
        assert mask_secret_value("ab") == "****ab"

    def test_empty(self):
        assert mask_secret_value("") == "****"
