import pytest

from app.core.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_is_not_plaintext_and_verifies() -> None:
    password = "StrongPassword123!"
    password_hash = hash_password(password)
    assert password_hash != password
    assert password_hash.startswith("$argon2")
    assert verify_password(password, password_hash) is True
    assert verify_password("wrong-password", password_hash) is False


def test_invalid_stored_hash_fails_closed() -> None:
    assert verify_password("anything", "TEST_ONLY_HASH") is False


def test_access_token_round_trip() -> None:
    token, expires_in = create_access_token(
        subject="11111111-1111-1111-1111-111111111111",
        organization_id="22222222-2222-2222-2222-222222222222",
        expires_minutes=5,
    )
    payload = decode_access_token(token)
    assert payload["sub"] == "11111111-1111-1111-1111-111111111111"
    assert payload["org"] == "22222222-2222-2222-2222-222222222222"
    assert payload["type"] == "access"
    assert expires_in == 300


def test_invalid_token_is_rejected() -> None:
    with pytest.raises(TokenError):
        decode_access_token("not-a-jwt")
