from app.core.transport_crypto import (
    decrypt_transport_field,
    encrypt_transport_field_for_tests,
    get_public_key_payload,
    is_transport_encrypted,
)


def test_transport_roundtrip():
    plain = "MyPass123"
    cipher = encrypt_transport_field_for_tests(plain)
    assert is_transport_encrypted(cipher)
    assert decrypt_transport_field(cipher) == plain


def test_public_key_payload_shape():
    payload = get_public_key_payload()
    assert payload["version"] == 1
    assert payload["algorithm"] == "RSA-OAEP-256+A256GCM"
    assert payload["prefix"] == "enc:v1:"
    assert "BEGIN PUBLIC KEY" in payload["public_key_pem"]
    assert payload["public_jwk"]["kty"] == "RSA"
    assert payload["public_jwk"]["alg"] == "RSA-OAEP-256"
