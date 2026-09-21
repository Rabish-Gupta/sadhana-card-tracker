from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher, extract_parameters
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from jwt import InvalidTokenError

from app.core.config import settings


_password_hasher = PasswordHasher()


class TokenError(ValueError):
    """Raised when an authentication token is invalid or expired."""


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_hash_needs_rehash(password_hash: str) -> bool:
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def password_hash_is_valid_argon2(password_hash: str) -> bool:
    """Return True only for a structurally valid Argon2 encoded hash.

    This is used by bootstrap/seed safeguards so placeholder strings such as
    TEST_ONLY_HASH can never be mistaken for a usable credential.
    """
    try:
        extract_parameters(password_hash)
    except (InvalidHashError, ValueError, TypeError):
        return False
    return password_hash.startswith(("$argon2id$", "$argon2i$", "$argon2d$"))


def create_access_token(
    *,
    subject: str,
    organization_id: str,
    expires_minutes: int | None = None,
) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    lifetime_minutes = expires_minutes or settings.access_token_expire_minutes
    expires_at = now + timedelta(minutes=lifetime_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "org": organization_id,
        "type": "access",
        "iat": now,
        "exp": expires_at,
    }
    encoded = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return encoded, lifetime_minutes * 60


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except InvalidTokenError as exc:
        raise TokenError("Invalid or expired access token") from exc

    if payload.get("type") != "access" or not payload.get("sub") or not payload.get("org"):
        raise TokenError("Invalid access token claims")
    return payload


def _main() -> None:
    parser = argparse.ArgumentParser(description="Security helper for local development")
    subparsers = parser.add_subparsers(dest="command", required=True)
    hash_parser = subparsers.add_parser("hash-password", help="Generate an Argon2 password hash")
    hash_parser.add_argument("password")
    args = parser.parse_args()

    if args.command == "hash-password":
        print(hash_password(args.password))


if __name__ == "__main__":
    _main()
