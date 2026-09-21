from sqlalchemy.orm import configure_mappers
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql

import app.models  # noqa: F401
from app.db.base import Base


def test_expected_core_tables_are_registered() -> None:
    configure_mappers()
    assert {
        "organizations",
        "users",
        "devotee_categories",
        "devotee_profiles",
        "devotee_category_history",
    }.issubset(Base.metadata.tables.keys())


def test_all_core_tables_compile_for_postgresql() -> None:
    configure_mappers()
    dialect = postgresql.dialect()
    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=dialect))
        assert f"CREATE TABLE {table.name}" in ddl


def test_category_history_allows_only_one_transition_per_effective_week() -> None:
    from app.models.devotee import DevoteeCategoryHistory

    constraint_names = {
        constraint.name
        for constraint in DevoteeCategoryHistory.__table__.constraints
        if constraint.name
    }
    assert "uq_category_history_profile_effective" in constraint_names
