from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import EmailStr

from app.core.enums import AccountStatus, RegistrationSource, UserRole
from app.schemas.base import ORMModel


class CategorySummary(ORMModel):
    id: uuid.UUID
    code: str
    display_name: str
    academic_year: int | None


class DevoteeProfilePublic(ORMModel):
    id: uuid.UUID
    college: str
    branch: str
    college_joining_year: int
    expected_graduation_year: int | None
    current_academic_year: int | None
    current_category: CategorySummary


class UserPublic(ORMModel):
    id: uuid.UUID
    full_name: str
    email: EmailStr
    phone_number: str
    role: UserRole
    account_status: AccountStatus
    registration_source: RegistrationSource
    approved_at: datetime | None
    deactivated_at: datetime | None
    created_at: datetime
    devotee_profile: DevoteeProfilePublic | None
