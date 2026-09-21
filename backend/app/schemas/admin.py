from __future__ import annotations

import re

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


_PHONE_RE = re.compile(r"^[+0-9][0-9 ()-]{6,29}$")


class AdminCreateDevoteeRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone_number: str = Field(min_length=7, max_length=30)
    college: str = Field(min_length=2, max_length=200)
    branch: str = Field(min_length=2, max_length=120)
    college_joining_year: int = Field(ge=2000, le=2100)
    category_code: str = Field(min_length=2, max_length=50)
    current_academic_year: int | None = Field(default=None, ge=1, le=4)

    @field_validator("full_name", "college", "branch", "category_code")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("category_code")
    @classmethod
    def normalize_category(cls, value: str) -> str:
        return value.upper()

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        value = value.strip()
        if not _PHONE_RE.fullmatch(value):
            raise ValueError("Invalid phone number format")
        return value


class RejectionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class AccountStatusChangeRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)

    @model_validator(mode="after")
    def strip_reason(self):
        self.reason = self.reason.strip()
        if len(self.reason) < 3:
            raise ValueError("Reason is required")
        return self
