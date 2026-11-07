from datetime import date

import pytest

from samovar_agent.domain.errors import QueryRejected
from samovar_agent.engine.parser import SqlParser
from samovar_agent.engine.queries import Queries
from samovar_agent.guard.sql_guard import GuardPolicy, SqlGuard
from tests.sql_files import cases

POLICY = GuardPolicy(
    window_days=31,
    views=frozenset({"mart.t", "mart.u", "dds.v", "dds.w"}),
)
WINDOW = dict(cases("guard-window"))


@pytest.fixture(scope="module")
def guard() -> SqlGuard:
    return SqlGuard(SqlParser(Queries.load()), lambda: date(2026, 10, 22))


@pytest.mark.parametrize(("label", "sql"), cases("guard-accepted"))
def test_guard_accepts_read_only_selects_over_dds_and_mart(guard: SqlGuard, label: str, sql: str) -> None:
    guard.check(sql, POLICY)


@pytest.mark.parametrize(("reason", "sql"), cases("guard-rejected"))
def test_guard_refuses_writes_settings_file_readers_and_foreign_relations(
    guard: SqlGuard, reason: str, sql: str
) -> None:
    with pytest.raises(QueryRejected, match=reason):
        guard.check(sql, POLICY)


@pytest.mark.parametrize(("label", "sql"), cases("guard-unfiltered-detail"))
def test_detail_queries_need_a_day_filter_next_to_the_table(guard: SqlGuard, label: str, sql: str) -> None:
    with pytest.raises(QueryRejected, match="must filter"):
        guard.check(sql, POLICY)


def test_detail_window_between_literal_days_is_limited(guard: SqlGuard) -> None:
    guard.check(WINDOW["31 days"], POLICY)
    with pytest.raises(QueryRejected, match="longer than 31 days"):
        guard.check(WINDOW["32 days"], POLICY)


def test_open_ended_literal_start_counts_up_to_today(guard: SqlGuard) -> None:
    with pytest.raises(QueryRejected, match="2026-09-01..2026-10-22"):
        guard.check(WINDOW["open start"], POLICY)


def test_day_column_comes_from_the_catalog(guard: SqlGuard) -> None:
    policy = GuardPolicy(window_days=31, date_columns={"dds.v": "event_day"}, views=POLICY.views)
    guard.check(WINDOW["custom day column"], policy)
    with pytest.raises(QueryRejected, match="by event_day"):
        guard.check(WINDOW["wrong day column"], policy)


def test_accepted_query_lists_views_but_not_ctes(guard: SqlGuard) -> None:
    accepted = guard.check(WINDOW["views but not CTEs"], POLICY)
    assert accepted.tables == ("mart.t", "mart.u")
    assert accepted.sql.endswith("using (dt)")


def test_empty_text_is_refused(guard: SqlGuard) -> None:
    with pytest.raises(QueryRejected, match="Empty"):
        guard.check(WINDOW["empty"], POLICY)


@pytest.mark.parametrize("case", ["computed start", "arithmetic on a literal", "text after the day", "computed end"])
def test_detail_bounds_must_be_date_literals_and_the_message_gives_today(guard: SqlGuard, case: str) -> None:
    with pytest.raises(QueryRejected, match="DATE literals only.*Today is 2026-10-22"):
        guard.check(WINDOW[case], POLICY)


def test_each_detail_table_of_a_join_needs_its_own_day_filter(guard: SqlGuard) -> None:
    with pytest.raises(QueryRejected, match="must filter dds.v"):
        guard.check(WINDOW["other table filtered"], POLICY)
    guard.check(WINDOW["both tables filtered"], POLICY)


def test_without_a_view_list_any_name_in_the_allowed_schemas_passes(guard: SqlGuard) -> None:
    guard.check(cases("guard-accepted")[0][1], GuardPolicy(window_days=31))
