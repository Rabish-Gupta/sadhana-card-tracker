from datetime import date, datetime, time, timezone

from app.core.enums import Weekday
from app.core.timezone import get_week_bounds, local_deadline_to_utc, organization_local_date


def test_monday_week_bounds() -> None:
    start, end = get_week_bounds(date(2026, 9, 17), Weekday.MONDAY)
    assert start == date(2026, 9, 14)
    assert end == date(2026, 9, 20)


def test_india_deadline_is_converted_to_utc() -> None:
    result = local_deadline_to_utc(date(2026, 9, 17), time(22, 0), "Asia/Kolkata")
    assert result == datetime(2026, 9, 17, 16, 30, tzinfo=timezone.utc)


def test_local_date_uses_organization_timezone() -> None:
    # 18:45 UTC is already the next calendar day in India.
    now = datetime(2026, 9, 17, 18, 45, tzinfo=timezone.utc)
    assert organization_local_date("Asia/Kolkata", now_utc=now) == date(2026, 9, 18)
