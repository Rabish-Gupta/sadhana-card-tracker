from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


def _json_value(value: Any) -> Any:
    """Recursively convert common domain values into JSONB-safe values.

    Audit payloads often contain nested lists/dicts of UUIDs, dates, Decimals, and
    enums. Keeping conversion recursive prevents an otherwise valid administrative
    correction from failing only when PostgreSQL serializes its before/after snapshot.
    """

    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    return value


def _json_safe(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if data is None:
        return None
    return {str(key): _json_value(value) for key, value in data.items()}


async def add_audit_log(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    reason: str | None = None,
    before_data: dict[str, Any] | None = None,
    after_data: dict[str, Any] | None = None,
    created_at: datetime | None = None,
) -> AuditLog:
    record = AuditLog(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        reason=reason,
        before_data=_json_safe(before_data),
        after_data=_json_safe(after_data),
        **({"created_at": created_at} if created_at is not None else {}),
    )
    session.add(record)
    return record
