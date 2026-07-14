from app.core.api_key_auth import generate_api_key, hash_api_key, mask_api_key
from app.core.config import settings


class TestGenerateApiKey:
    def test_format_sk_prefix_and_length(self):
        key = generate_api_key()
        assert key.startswith(settings.api_key_prefix)
        # sk- + 32 hex
        assert len(key) == len(settings.api_key_prefix) + 32
        hex_part = key[len(settings.api_key_prefix) :]
        assert len(hex_part) == 32
        int(hex_part, 16)  # raises if not hex

    def test_unique(self):
        keys = {generate_api_key() for _ in range(20)}
        assert len(keys) == 20


class TestMaskApiKey:
    def test_mask_shape(self):
        key = "sk-a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
        masked = mask_api_key(key)
        assert masked == "sk-a1b2...o5p6"
        assert "..." in masked

    def test_short_or_empty(self):
        assert mask_api_key("") == "****"
        assert mask_api_key("short") == "****"
        assert mask_api_key(None) == "****"


class TestHashApiKey:
    def test_hash_length_and_stable(self):
        key = "sk-deadbeefdeadbeefdeadbeefdeadbeef"
        h1 = hash_api_key(key)
        h2 = hash_api_key(key)
        assert h1 == h2
        assert len(h1) == 32
        assert h1 != key

    def test_different_keys_differ(self):
        assert hash_api_key("sk-aaa") != hash_api_key("sk-bbb")
