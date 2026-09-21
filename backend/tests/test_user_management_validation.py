import uuid

import pytest

from app.models.devotee import DevoteeCategory
from app.services.users import CategoryValidationError, _validate_academic_year


def category(code: str, academic_year: int | None) -> DevoteeCategory:
    return DevoteeCategory(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        code=code,
        display_name=code.title(),
        academic_year=academic_year,
        stage_order=1,
        is_active=True,
        is_archived=False,
    )


def test_student_category_requires_matching_academic_year() -> None:
    arjuna = category("ARJUNA", 3)
    _validate_academic_year(arjuna, 3)
    with pytest.raises(CategoryValidationError):
        _validate_academic_year(arjuna, 2)
    with pytest.raises(CategoryValidationError):
        _validate_academic_year(arjuna, None)


def test_bhima_category_must_not_have_current_academic_year() -> None:
    bhima = category("BHIMA_WORKING", None)
    _validate_academic_year(bhima, None)
    with pytest.raises(CategoryValidationError):
        _validate_academic_year(bhima, 4)
