from app.core.security import (
    hash_password,
    password_hash_is_valid_argon2,
    verify_password,
)


def test_seed_password_helper_accepts_real_argon2_hash() -> None:
    password = "AdminTest123!"
    encoded = hash_password(password)

    assert encoded.startswith("$argon2")
    assert password_hash_is_valid_argon2(encoded) is True
    assert verify_password(password, encoded) is True


def test_seed_password_helper_rejects_placeholder_and_plaintext() -> None:
    assert password_hash_is_valid_argon2("TEST_ONLY_HASH") is False
    assert password_hash_is_valid_argon2("AdminTest123!") is False
    assert password_hash_is_valid_argon2("") is False
