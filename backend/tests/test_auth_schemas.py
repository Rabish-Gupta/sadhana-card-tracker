import pytest
from pydantic import ValidationError

from app.schemas.admin import AccountStatusChangeRequest, AdminCreateDevoteeRequest
from app.schemas.auth import RegistrationRequest


def valid_registration() -> dict:
    return {
        "full_name": "Madhav Das",
        "email": "madhav@example.com",
        "password": "StrongPass123!",
        "phone_number": "+91 9876543210",
        "college": "Example Institute of Technology",
        "branch": "Computer Science",
        "current_academic_year": 3,
        "college_joining_year": 2024,
    }


def test_registration_requires_valid_academic_year() -> None:
    data = valid_registration()
    data["current_academic_year"] = 5
    with pytest.raises(ValidationError):
        RegistrationRequest.model_validate(data)


def test_registration_requires_reasonable_password_length() -> None:
    data = valid_registration()
    data["password"] = "short"
    with pytest.raises(ValidationError):
        RegistrationRequest.model_validate(data)


def test_admin_category_code_is_normalized() -> None:
    payload = AdminCreateDevoteeRequest(
        full_name="Bhima Das",
        email="bhima@example.com",
        password="StrongPass123!",
        phone_number="+919876543210",
        college="Example College",
        branch="CSE",
        college_joining_year=2020,
        category_code="bhima_working",
        current_academic_year=None,
    )
    assert payload.category_code == "BHIMA_WORKING"


def test_deactivation_reason_is_required() -> None:
    with pytest.raises(ValidationError):
        AccountStatusChangeRequest(reason="  ")
