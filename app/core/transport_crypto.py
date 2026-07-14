"""传输层加密：前端用服务端公钥加密敏感字段，后端解密后再业务处理。

密文格式: enc:v1:<base64url(JSON)>
JSON: {"ek": "...", "iv": "...", "ct": "..."}
  - ek: RSA-OAEP-SHA256 加密的 AES-256 密钥 (base64)
  - iv: AES-GCM 12 字节 nonce (base64)
  - ct: ciphertext || tag (base64)，与 Web Crypto AES-GCM 一致
"""

from __future__ import annotations

import base64
import json
import threading
from pathlib import Path
from typing import Annotated

import structlog
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BeforeValidator

from app.core.config import settings

logger = structlog.get_logger()

TRANSPORT_PREFIX = "enc:v1:"
_RSA_KEY_BITS = 2048
_lock = threading.Lock()
_private_key: rsa.RSAPrivateKey | None = None


def _b64e(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64d(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"))


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _key_path() -> Path:
    return Path(settings.upload_base_dir) / ".transport_rsa.pem"


def _load_or_create_private_key() -> rsa.RSAPrivateKey:
    global _private_key
    if _private_key is not None:
        return _private_key

    with _lock:
        if _private_key is not None:
            return _private_key

        pem = (settings.transport_rsa_private_key_pem or "").strip()
        if pem:
            pem = pem.replace("\\n", "\n")
            _private_key = serialization.load_pem_private_key(
                pem.encode("utf-8"), password=None
            )
            logger.info("transport_rsa_loaded", source="env")
            return _private_key

        path = _key_path()
        if path.exists():
            _private_key = serialization.load_pem_private_key(
                path.read_bytes(), password=None
            )
            logger.info("transport_rsa_loaded", source=str(path))
            return _private_key

        key = rsa.generate_private_key(public_exponent=65537, key_size=_RSA_KEY_BITS)
        pem_bytes = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pem_bytes)
        path.chmod(0o600)
        _private_key = key
        logger.warning(
            "transport_rsa_generated",
            path=str(path),
            hint="生产环境请设置 TRANSPORT_RSA_PRIVATE_KEY_PEM",
        )
        return _private_key


def get_public_jwk() -> dict:
    """返回 Web Crypto 可用的 RSA-OAEP public JWK。"""
    private_key = _load_or_create_private_key()
    public_key = private_key.public_key()
    numbers = public_key.public_numbers()

    def int_to_b64url(value: int, length: int | None = None) -> str:
        raw = value.to_bytes(length or (value.bit_length() + 7) // 8, "big")
        return _b64url_encode(raw)

    n_len = (_RSA_KEY_BITS + 7) // 8
    return {
        "kty": "RSA",
        "alg": "RSA-OAEP-256",
        "ext": True,
        "key_ops": ["encrypt"],
        "n": int_to_b64url(numbers.n, n_len),
        "e": int_to_b64url(numbers.e),
        "kid": "transport-v1",
        "use": "enc",
    }


def get_public_key_payload() -> dict:
    private_key = _load_or_create_private_key()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return {
        "version": 1,
        "algorithm": "RSA-OAEP-256+A256GCM",
        "prefix": TRANSPORT_PREFIX,
        "public_key_pem": public_pem,
        "public_jwk": get_public_jwk(),
    }


def is_transport_encrypted(value: str) -> bool:
    return isinstance(value, str) and value.startswith(TRANSPORT_PREFIX)


def decrypt_transport_field(value: str) -> str:
    """解密传输密文；非密文时按配置决定是否允许明文。"""
    if not isinstance(value, str):
        raise ValueError("敏感字段必须是字符串")

    if not is_transport_encrypted(value):
        if settings.transport_require_encryption:
            raise ValueError("敏感字段必须使用传输加密，格式: enc:v1:...")
        return value

    try:
        payload = json.loads(_b64url_decode(value[len(TRANSPORT_PREFIX) :]).decode("utf-8"))
        ek = _b64d(payload["ek"])
        iv = _b64d(payload["iv"])
        ct = _b64d(payload["ct"])
    except (KeyError, ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError("传输密文格式无效，请重新获取公钥后加密") from e

    private_key = _load_or_create_private_key()
    try:
        aes_key = private_key.decrypt(
            ek,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        plain = AESGCM(aes_key).decrypt(iv, ct, None)
    except Exception as e:
        logger.warning("transport_decrypt_failed", error=str(e))
        # 常见于多 worker 未共享同一 TRANSPORT_RSA_PRIVATE_KEY_PEM
        raise ValueError(
            "传输密文解密失败，请重新调用 /api/crypto/public-key 后加密提交"
        ) from e

    return plain.decode("utf-8")


def encrypt_transport_field_for_tests(plaintext: str) -> str:
    """仅用于测试：用当前公钥流程加密。"""
    import os

    private_key = _load_or_create_private_key()
    public_key = private_key.public_key()
    aes_key = AESGCM.generate_key(bit_length=256)
    iv = os.urandom(12)
    ct = AESGCM(aes_key).encrypt(iv, plaintext.encode("utf-8"), None)
    ek = public_key.encrypt(
        aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    blob = json.dumps(
        {"ek": _b64e(ek), "iv": _b64e(iv), "ct": _b64e(ct)},
        separators=(",", ":"),
    ).encode("utf-8")
    return TRANSPORT_PREFIX + _b64url_encode(blob)


def _sensitive_before(value: str | None) -> str | None:
    if value is None:
        return None
    return decrypt_transport_field(value)


SensitiveStr = Annotated[str, BeforeValidator(_sensitive_before)]


def decrypt_sensitive_dict_fields(data: dict | None, keys: tuple[str, ...]) -> dict | None:
    if not data:
        return data
    out = dict(data)
    for key in keys:
        if key in out and out[key] is not None:
            out[key] = decrypt_transport_field(str(out[key]))
    return out
