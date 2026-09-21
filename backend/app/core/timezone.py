from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.enums import Weekday


class InvalidTimezoneError(ValueError):
    pass


def get_zoneinfo(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise InvalidTimezoneError(f"Unknown IANA timezone: {timezone_name}") from exc


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_organization_time(value: datetime, timezone_name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Datetime must be timezone-aware")
    return value.astimezone(get_zoneinfo(timezone_name))


def organization_local_now(timezone_name: str, *, now_utc: datetime | None = None) -> datetime:
    value = now_utc or utc_now()
    return to_organization_time(value, timezone_name)


def organization_local_date(timezone_name: str, *, now_utc: datetime | None = None) -> date:
    return organization_local_now(timezone_name, now_utc=now_utc).date()


def get_week_bounds(local_date: date, week_start_day: int | Weekday) -> tuple[date, date]:
    """Return organization-local inclusive week bounds.

    Project numbering: Sunday=0, Monday=1, ..., Saturday=6.
    Python date.weekday(): Monday=0, ..., Sunday=6.
    """
    start_day = int(week_start_day)
    if not 0 <= start_day <= 6:
        raise ValueError("week_start_day must be between 0 and 6")

    python_day_as_sunday_zero = (local_date.weekday() + 1) % 7
    days_since_start = (python_day_as_sunday_zero - start_day) % 7
    week_start = local_date - timedelta(days=days_since_start)
    return week_start, week_start + timedelta(days=6)


def local_deadline_to_utc(card_date: date, deadline: time, timezone_name: str) -> datetime:
    """Convert an organization-local card deadline to an absolute UTC timestamp.

    The resolved timestamp should be snapshotted on each daily card so later timezone
    or deadline configuration changes cannot reinterpret historical deadlines.
    """
    zone = get_zoneinfo(timezone_name)
    local_datetime = datetime.combine(card_date, deadline, tzinfo=zone)
    return local_datetime.astimezone(timezone.utc)
