from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.enums import AccountStatus


_PHONE_RE = re.compile(r"^[+0-9][0-9 ()-]{6,29}$")


class RegistrationRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone_number: str = Field(min_length=7, max_length=30)
    college: str = Field(min_length=2, max_length=200)
    branch: str = Field(min_length=2, max_length=120)
    current_academic_year: int = Field(ge=1, le=4)
    college_joining_year: int = Field(ge=2000, le=2100)

    @field_validator("full_name", "college", "branch")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        value = value.strip()
        if not _PHONE_RE.fullmatch(value):
            raise ValueError("Invalid phone number format")
        return value


class RegistrationResponse(BaseModel):
    user_id: uuid.UUID
    email: EmailStr
    account_status: AccountStatus
    message: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ApprovalResponse(BaseModel):
    user_id: uuid.UUID
    account_status: AccountStatus
    approved_at: datetime | None = None


class LogoutResponse(BaseModel):
    message: str
