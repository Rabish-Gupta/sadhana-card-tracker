from enum import Enum, IntEnum


class Weekday(IntEnum):
    """Organization-local weekday numbering used by the project.

    Deliberately uses Sunday=0 to match the approved database design.
    """

    SUNDAY = 0
    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6


class UserRole(str, Enum):
    DEVOTEE = "DEVOTEE"
    ADMIN = "ADMIN"


class AccountStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    REJECTED = "REJECTED"


class RegistrationSource(str, Enum):
    SELF_REGISTERED = "SELF_REGISTERED"
    ADMIN_CREATED = "ADMIN_CREATED"


class ChangeSource(str, Enum):
    SYSTEM = "SYSTEM"
    ADMIN = "ADMIN"
    DEVOTEE = "DEVOTEE"


class EmploymentStatus(str, Enum):
    WORKING = "WORKING"
    NOT_WORKING = "NOT_WORKING"


class ActivityCategory(str, Enum):
    SADHANA = "SADHANA"
    ACADEMIC = "ACADEMIC"


class ScoringType(str, Enum):
    DAILY = "DAILY"
    WEEKLY_AGGREGATED = "WEEKLY_AGGREGATED"
    NON_SCORED = "NON_SCORED"
    SYSTEM_DERIVED = "SYSTEM_DERIVED"


class AggregationMethod(str, Enum):
    SUM = "SUM"
    AVERAGE = "AVERAGE"
    COUNT = "COUNT"
    MIN = "MIN"
    MAX = "MAX"


class RuleType(str, Enum):
    BOOLEAN = "BOOLEAN"
    THRESHOLD = "THRESHOLD"
    PERCENTAGE = "PERCENTAGE"
    SYSTEM_DERIVED = "SYSTEM_DERIVED"
    NO_SCORE = "NO_SCORE"


class VersionStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class ActivityInputType(str, Enum):
    NUMBER = "NUMBER"
    COUNT = "COUNT"
    DURATION = "DURATION"
    TIME = "TIME"
    BOOLEAN = "BOOLEAN"
    TEXT = "TEXT"
    SELECTION = "SELECTION"


class StandardPeriod(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"


class CardStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    FINALIZED = "FINALIZED"


class RoundingMode(str, Enum):
    HALF_UP = "HALF_UP"
